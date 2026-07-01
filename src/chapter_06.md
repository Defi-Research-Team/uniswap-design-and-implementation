# Oracle

This chapter unfolds Uniswap V2's _oracle_ mechanism. The pool, in `_update`, additionally accumulates two variables: `price0CumulativeLast` and `price1CumulativeLast` — these are the entirety of the raw price data V2 provides to external protocols. This chapter first gives the definition of the _Time-Weighted Average Price (TWAP)_, then follows the thread of "what data is needed to compute it," revealing how these two accumulators record price, and finally analyzes why TWAP can resist manipulation by a single trade.

## The Fragility of the Spot Price

Many DeFi protocols (lending, derivatives, stablecoins, etc.) need an external price to decide liquidations, mints, or settlements. Every Uniswap Pair can provide a price at any time: the ratio of reserves $\text{reserve1}/\text{reserve0}$, i.e., the _spot price_. It is convenient to obtain, yet extremely dangerous.

The problem is that the spot price can be rewritten instantly by a single trade. An attacker can use a _flash loan_ to borrow a huge amount of capital and, within a single block, launch a massive `swap` against a Pair, pushing the spot price to an extreme value; the protocol depending on that price then makes an erroneous decision (such as issuing an over-collateralized loan), and the attacker pushes the price back and repays the flash loan within the same transaction. The whole process completes within a single transaction, and the attacker bears almost no cost — this is the notorious oracle manipulation attack.

Therefore, directly reading the spot price cannot serve as a trusted price source. We need a price that is immune to "single-block instantaneous manipulation": the time-weighted average price.

## Time-Weighted Average Price

A TWAP is simply the average of prices over a time window, weighted by how long each price persisted. Suppose that within the window $[t_1, t_2]$ the price is not constant but rather piecewise-constant: in segment $i$ the price is $P_i$ for a duration of $\Delta t_i$. Then the TWAP over this window is:

$$\text{TWAP} = \frac{\sum P_i \cdot \Delta t_i}{\sum \Delta t_i} = \frac{\sum P_i \cdot \Delta t_i}{t_2 - t_1} \tag{1}$$

The denominator $\sum \Delta t_i$ is the total window length $t_2 - t_1$, and the numerator is the discrete integral of price over time. This is exactly the meaning of "time-weighted": the longer a price persists, the greater its weight in the numerator and its influence on the average.

For example: if the price of token0 was 2000 for the past 1 hour (3600 seconds) and was then instantly pushed to 2500 by a large trade, holding that value for the remaining 12 seconds of the current block, then by Equation (1), the TWAP over this 3612-second window is $\frac{2000 \times 3600 + 2500 \times 12}{3612} \approx 2001.66$. A trade that pushed the price up by 25% affects the window's average by less than 0.1%, because that high-price spike occupied only 12 of the 3612 seconds. The instantaneous manipulation is diluted by time.

The question then naturally arises: to compute this TWAP, what data exactly does the contract need to record for this purpose?

## Price Accumulators

To compute the numerator $\sum P_i \cdot \Delta t_i$ of Equation (1), the most naive approach would be to record each segment's price and duration as a pair. But this is impractical: reserves change with every `swap`, and the price changes accordingly; recording each one would cause storage costs to grow unboundedly with the number of trades, with no way to compress.

The key observation is that we do not care about "each segment" individually, only their sum. We can therefore keep accumulating "price × duration" into a single running variable $C$, whose value at time $t$ is exactly the price integral up to that moment, $C(t) = \sum P_i \cdot \Delta t_i$. The numerator over any window $[t_1, t_2]$ is simply the difference of two moments, $C(t_2) - C(t_1)$. This way, the contract only needs to maintain one ever-growing accumulator; external readers take a snapshot at each end and subtract, obtaining the exact price integral — with no need for per-trade storage or any historical list.

This is exactly V2's approach. The Pair continuously accumulates price in `_update`:

```solidity
// v2-core/contracts/UniswapV2Pair.sol

uint32 timeElapsed = blockTimestamp - blockTimestampLast; // overflow is desired
if (timeElapsed > 0 && _reserve0 != 0 && _reserve1 != 0) {
    // * never overflows, and + overflow is desired
    price0CumulativeLast += uint(UQ112x112.encode(_reserve1).uqdiv(_reserve0)) * timeElapsed;
    price1CumulativeLast += uint(UQ112x112.encode(_reserve0).uqdiv(_reserve1)) * timeElapsed;
}
```

What `price0CumulativeLast` accumulates is "the price of token0 in terms of token1" multiplied by the duration — the $C(t)$ above. Here `UQ112x112.encode(_reserve1).uqdiv(_reserve0)` is exactly the Chapter 2 `UQ112.112` fixed-point representation of the price $\text{reserve1}/\text{reserve0}$, and `timeElapsed` is the number of seconds since the last update. So, each time reserves are updated for the **first** time in a block, the contract multiplies the price that was actually in effect during the previous period by how long it lasted and adds it to the accumulator:

$$\text{price0CumulativeLast} \mathrel{+}= \frac{\text{reserve1}}{\text{reserve0}} \times \Delta t \tag{2}$$

Note a few key points:

- **Accumulated only once per block**: `timeElapsed > 0` ensures that only the first `_update` upon entering a new block performs the accumulation, avoiding double-counting multiple trades within the same block.
- **Priced using old reserves**: the accumulation uses `_reserve0`/`_reserve1` (the pre-update reserves), i.e., "the price that was actually in effect during the previous period," not the instantaneous post-trade price.
- **Overflow is intentional**: the accumulators are stored as `uint` (256 bits) and naturally wrap around. Since external usage only needs the difference of two moments, wrapping does not affect the result — this is a property of unsigned integer difference arithmetic.

Substituting Equation (2) back into Equation (1): since $C(t_2) - C(t_1)$ is the numerator, the TWAP over any window can be obtained directly from two snapshots of the accumulator:

$$\text{TWAP} = \frac{\text{price0CumulativeLast}(t_2) - \text{price0CumulativeLast}(t_1)}{t_2 - t_1} \tag{3}$$

These two accumulators constitute the entirety of the oracle data a Pair provides: the Pair is responsible only for faithfully accumulating and computes no average — the averaging work is entirely delegated to external readers (how readers sample and compute the TWAP over periodic or sliding windows will be covered when analyzing the periphery contracts).

## Manipulation-Resistance Analysis

The reason TWAP is manipulation-resistant lies in "time-weighting": to shift the average price, an attacker must make the deviating price **persist**, not merely appear instantaneously.

![TWAP manipulation resistance](images/ch06/twap.png)

*Figure 1　TWAP diluting single-block manipulation. Top: the spot price (thin line) is instantly pushed to a spike by a single trade within a block and then pulled back by arbitrageurs, while the cumulative price (thick line) grows only by a tiny amount due to this spike; bottom: the TWAP (solid line) derived from it is nearly unchanged, always close to the true value (dashed line). To significantly raise the TWAP, an attacker must sustain the high price over a large portion of the window's duration.*

If an attacker wants to raise the TWAP by $\delta$ over a window of $T$ seconds, they must sustain the spot price at a high level for roughly $T \cdot (\delta/\text{deviation magnitude})$ seconds. For each additional block sustained, they bear a twofold cost: first, the massive price impact required to push the price away from equilibrium (capital locked in a losing position), and second, the arbitrageurs who continually pull the price back, extracting profit from them. Thus the manipulation cost is roughly proportional to pool liquidity × window duration × desired deviation — the longer the window and the deeper the pool, the more expensive the manipulation.

This precisely closes off the foundation of flash-loan attacks: a flash loan can only take effect within a single transaction (a single block), and a single-block price spike is diluted by the long window to near-insignificance. The attacker cannot "borrow, manipulate, repay" in one go; they must expose their capital and risk over multiple blocks, rendering the attack uneconomical.

## Summary

The spot price can be instantaneously manipulated by a flash loan within a single block and thus cannot directly serve as a trusted price source — which motivates the time-weighted average price, immune to single-block manipulation. A TWAP averages the prices over a window weighted by their duration; the longer a price persists, the greater its weight, and a fleeting price spike barely affects the window's average. To compute the TWAP, V2 has the Pair continuously accumulate "price × duration" into two accumulators in `_update` — accumulated once per block's first update, priced using pre-update reserves, with intentional overflow. External readers take a snapshot at each of two moments, subtract, and divide by the time difference to obtain the TWAP; the Pair is responsible only for faithful accumulation. Precisely because of this, manipulating the TWAP requires sustaining a deviating price over multiple blocks, with cost roughly proportional to the pool's liquidity, the window's duration, and the desired deviation, so flash-loan-style single-block attacks are diluted by time and rendered ineffective.
