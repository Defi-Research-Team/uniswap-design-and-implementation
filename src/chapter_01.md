# Automated Market Makers

We begin with one of the most fundamental and important concepts in DeFi — the Automated Market Maker (AMM).

If you have used Uniswap, SushiSwap, or other DEXes for token swaps, you have already interacted with an AMM. But what are the mathematical principles behind AMMs? Why can they enable trading without traditional buyers and sellers placing orders? Why might liquidity providers face "impermanent loss"? This chapter will answer these questions one by one, laying the theoretical foundation for our subsequent deep dive into Uniswap's contract implementations.

## Market Makers

Before understanding "automated" market makers, we need to understand what a "market maker" is.

### What is a Market Maker

In financial markets, a **market maker** is an institution or individual that continuously provides buy and sell quotes for an asset. Market makers simultaneously place orders on both the buy and sell sides, committing to buy or sell a certain quantity of the asset at quoted prices, thereby providing **liquidity** to the market.

"Liquidity" refers to the ability of an asset to be bought or sold quickly at a reasonable price. In a market with good liquidity, traders can complete transactions at prices close to the current market price at any time, with minimal price impact even for large trades. In a market with poor liquidity, traders may need to wait a long time to find a counterparty, or be forced to accept prices far from the market price.

A market maker's profit model is straightforward: buy at a lower price (bid), sell at a higher price (ask), and the difference between the two — the **spread** — is the market maker's source of profit.

For example, a market maker's quote for ETH might be:

```
Bid        Ask
$2,000.00  $2,000.50
```

This means the market maker is willing to buy ETH at $2,000.00 and sell ETH at $2,000.50. If someone sells to the market maker at $2,000.00, and another person buys from the market maker at $2,000.50, the market maker earns a spread of $0.50.

### The Role of Market Makers

Market makers play a critical role in financial markets:

- **Providing liquidity**: Traders don't need to wait for a counterparty to appear; they can trade with the market maker at any time
- **Narrowing spreads**: Competition among multiple market makers drives bid-ask spreads tighter
- **Smoothing price volatility**: Market makers absorb buying and selling pressure through continuous quoting, reducing sharp price movements

Of course, market makers also face risks: if market prices move rapidly, the market maker's inventory may depreciate, resulting in losses. Therefore, professional market makers require sophisticated risk management strategies and the ability to quickly adjust their quotes.

## The Order Book Model

Having understood the concept of market makers, let's examine the traditional trading model — the order book.

### How Order Books Work

An **order book** is the most fundamental trading mechanism in traditional financial markets. It records all outstanding buy and sell orders, arranged by price:

```
Bids (Buy)          Asks (Sell)
─────────           ─────────
Price  Qty          Price  Qty
100    5            101    3
 99   10            102    7
 98    8            103   12
```

- **Bid**: A buyer's offer to purchase a certain quantity of an asset at a specific price
- **Ask**: A seller's offer to sell a certain quantity of an asset at a specific price
- **Matching**: When a bid price ≥ an ask price, the exchange automatically matches them for execution

In the order book model, market makers provide liquidity by simultaneously placing orders on both the buy and sell sides. Regular traders execute trades by submitting orders that match against the market maker's or other traders' resting orders.

### The On-Chain Dilemma of Order Books

The order book model works well in centralized exchanges (such as Binance, Coinbase), but faces fundamental challenges in a decentralized blockchain environment:

- **High gas costs**: Every order placement, cancellation, and matching is an on-chain transaction requiring gas fees. Market makers typically need to adjust quotes frequently (potentially hundreds of times per second), making on-chain execution prohibitively expensive
- **Liquidity fragmentation**: A single trading pair has many price levels, with liquidity scattered across different prices. On-chain liquidity is already limited, and further fragmentation leads to a worse trading experience
- **Slow execution speed**: Block confirmation times (about 12 seconds on Ethereum) are far slower than centralized exchanges (microsecond-level), preventing market makers from responding to market changes in a timely manner

These challenges may be acceptable for low-frequency, large-value trades, but for the DeFi vision of "any token pair, any time, instant trading," the order book model falls short.

This raises a key question: **Can we design an on-chain trading mechanism that doesn't require buy/sell orders from both parties, nor professional market makers continuously quoting?**

## Automated Market Makers

The Automated Market Maker (AMM) offers a fundamentally different answer: **no order book, no traditional market maker — instead, mathematical formulas and liquidity pools determine prices**.

### Core Ideas of AMMs

The core ideas of AMMs can be summarized as follows:

1. **Liquidity pools**: Create a pool for each trading pair, holding two tokens (e.g., ETH and USDC)
2. **Mathematical formula**: Use a mathematical formula to define the relationship between the quantities of the two tokens in the pool, which determines the exchange price
3. **Trade anytime**: When someone wants to swap token A for token B, they swap directly from the pool at the formula-calculated price, without waiting for a counterparty
4. **Anyone can be a market maker**: Anyone can deposit two tokens into a pool to become a liquidity provider (LP) and earn trading fees

The key difference from the order book model is: **AMMs have no orders; prices are entirely determined by mathematical formulas and the ratio of assets in the pool**. This means trades don't need to wait for a counterparty — as long as the pool has sufficient liquidity, swaps can be completed at any time.

From a market maker's perspective, AMMs "automate" the role of market making. Traditional market makers need professional teams and complex strategies to continuously quote, whereas in AMMs, mathematical formulas replace quoting strategies, LP deposits replace market maker inventory, and the price discovery process is fully automated.

### Multiple AMM Models

AMM is not a single fixed model, but rather a general term for a class of market-making mechanisms driven by mathematical formulas. Different formulas define different price curves and liquidity distribution characteristics. Common AMM models include:

- **Constant Product Market Maker (CPMM)**: $x \cdot y = k$, with a hyperbolic price curve. This is the most classic AMM model, adopted by major DEXes such as Uniswap V2, SushiSwap, and PancakeSwap
- **Constant Sum Market Maker (CSMM)**: $x + y = k$, with a constant price that produces no slippage but will deplete one token's reserves in the pool
- **Constant Mean Market Maker (CMMM)**: A model proposed by Balancer that supports pools with more than two tokens and allows custom weights for each token
- **Hybrid AMM**: Combines the advantages of multiple models. For example, Curve's StableSwap combines constant sum and constant product for stablecoin pairs, providing extremely low slippage when prices are close to 1:1

Each model has its own strengths and is suited for different trading scenarios. Among them, the **Constant Product Market Maker (CPMM)** has become the most widely adopted AMM model due to its simple mathematical form, good price discovery properties, and generality for any token pair. Uniswap, as the most successful DEX protocol, is built on the CPMM foundation.

## Constant Product Market Maker (CPMM)

### Definition

Suppose a liquidity pool contains two tokens X and Y, with quantities $x$ and $y$ respectively. The constant product formula states:

$$x \cdot y = k$$

where $k$ is a constant that remains unchanged before and after trades.

We define the following terms:

- **Reserves**: The quantities $x$ and $y$ of tokens X and Y in the pool
- **Invariant**: $k = x \cdot y$, which remains constant during trades
- **Liquidity**: $L = \sqrt{xy} = \sqrt{k}$, measuring the total scale of funds in the pool
- **Price**: $P = y / x$, i.e., the price of token Y relative to token X

The core meaning of the constant product formula is: **swaps do not change liquidity** — no matter how much token X a trader swaps for token Y, the product of the two token quantities $xy$ always equals $k$, and liquidity $L$ remains unchanged. When one token increases in the pool, the other necessarily decreases proportionally, but this is merely a conversion of asset form; the total liquidity of the pool remains the same.

### Deriving the Token Swap Formula

Let's derive the token swap formula based on the constant product constraint.

Suppose a user wants to swap $\Delta x$ of token X for token Y. After the swap, the pool's token X quantity becomes $x + \Delta x$, and the token Y quantity must decrease by $\Delta y$. According to the constant product constraint (i.e., liquidity remains unchanged):

$$(x + \Delta x)(y - \Delta y) = k = x \cdot y$$

Expanding the left side:

$$xy - x \cdot \Delta y + \Delta x \cdot y - \Delta x \cdot \Delta y = x \cdot y$$

Cancel $xy$ from both sides:

$$-x \cdot \Delta y + \Delta x \cdot y - \Delta x \cdot \Delta y = 0$$

Rearranging:

$$x \cdot \Delta y = \Delta x \cdot (y - \Delta y)$$

$$\Delta y = \frac{\Delta x \cdot y}{x + \Delta x}$$

This is the core swap formula of CPMM: **the amount of token Y $\Delta y$ that can be obtained with $\Delta x$ of token X is entirely determined by the current reserves of the two tokens in the pool**. Note that this derivation does not account for fees.

### Intuitive Understanding

While mathematical formulas are precise, intuitive understanding is equally important. We can understand $x \cdot y = k$ from two perspectives:

**Perspective 1: Constant Product**

The product of the two token quantities in the pool remains unchanged before and after trades. If the pool has 100 ETH and 200,000 USDC, then $k = 100 \times 200000 = 20,000,000$. Regardless of how many trades occur, as long as no liquidity is added or removed, the product of ETH and USDC quantities always equals 20,000,000.

**Perspective 2: Hyperbolic Constraint**

On a plane with $x$ and $y$ as coordinate axes, $x \cdot y = k$ is a hyperbola. The quantities of the two tokens in the pool always move along this curve. When one token increases, the other necessarily decreases — this is the essence of "swapping."

```
  y
  │╲
  │  ╲
  │    ╲
  │      ╲
  │        ╲
  │          ╲
  │            ╲
  │              ╲
  └────────────────╲ x
     x·y = k (hyperbola)
```

### Simple Example

Suppose an ETH/USDC pool has 10 ETH and 20,000 USDC, $k = 200,000$.

**Scenario**: Alice wants to swap 1 ETH for USDC.

According to the formula:

$$\Delta y = \frac{\Delta x \cdot y}{x + \Delta x} = \frac{1 \times 20000}{10 + 1} = \frac{20000}{11} \approx 1818.18 \text{ USDC}$$

Pool state after the trade:
- ETH: $10 + 1 = 11$
- USDC: $20000 - 1818.18 = 18181.82$
- Verification: $11 \times 18181.82 = 200000$ ✓

Note that at the pre-trade "price" ($20000/10 = 2000$ USDC/ETH), 1 ETH should be worth 2000 USDC. But in reality, only 1818.18 USDC was received — nearly 182 USDC less. This difference is caused by **slippage** and **price impact**, which we'll analyze in detail later.

## Price Discovery Mechanism

### Reserve Ratio as Price

In CPMM, the "price" of a token is implicitly determined by the reserve ratio of the two tokens in the pool.

Consider a limiting case: when the swap amount $\Delta x$ is extremely small, the formula approximates:

$$\frac{\Delta y}{\Delta x} \approx \frac{y}{x}$$

That is, **the marginal price equals the reserve ratio**. In the previous example:

- Before trade: price = $y/x = 20000/10 = 2000$ USDC/ETH
- After trade: price = $y'/x' = 18181.82/11 \approx 1652.89$ USDC/ETH

We can see that the trade caused ETH to depreciate relative to USDC (from 2000 to 1652.89), which is consistent with supply and demand: there's more ETH in the pool, so its "price" naturally decreases.

This is the AMM's **automatic price discovery**: no external price input is needed — the asset ratio in the pool is itself the price. When external market prices change, arbitrageurs will trade to pull the pool's price back in line with the market — this process is automatic and trustless.

### Slippage and Price Impact

**Slippage** refers to the difference between a trade's expected price and its actual execution price.

Returning to the earlier example: Alice swapped 1 ETH for USDC. The pre-trade price was 2000 USDC/ETH, but she actually received only 1818.18 USDC. The effective exchange rate was:

$$\text{Effective price} = \frac{1818.18}{1} = 1818.18 \text{ USDC/ETH}$$

$$\text{Slippage} = \frac{2000 - 1818.18}{2000} = 9.09\%$$

**Price impact** refers to the magnitude of the pool's price change caused by a single trade.

$$\text{Price impact} = \frac{|P_{\text{new}} - P_{\text{old}}|}{P_{\text{old}}} = \frac{|1652.89 - 2000|}{2000} = 17.36\%$$

Slippage and price impact are related but distinct concepts:
- **Price impact** measures "how much the price changed" — focusing on the pool's state change
- **Slippage** measures "how much less I actually received compared to expectations" — focusing on the trader's cost

Both reflect the pool's **liquidity depth**. The more funds in the pool (the larger $k$), the less slippage and price impact for the same trade size.

### Brief Note on Fees

So far we have ignored fees. In practice, AMMs charge a percentage fee on each trade (e.g., Uniswap V2 charges 0.3%), which is distributed to all LPs. When fees are included, the swap formula becomes more complex and will be derived in detail in the V2 chapters.

## Liquidity Management

Earlier we defined liquidity as $L = \sqrt{xy}$ and stated that trades do not change liquidity. How is liquidity created and managed? What constraints must liquidity providers follow when adding assets to a pool?

### Constraints for Adding Liquidity

Adding liquidity to a pool with existing reserves essentially means simultaneously increasing both token quantities. Suppose the pool currently has $x$ of token X and $y$ of token Y, with price $P = y/x$ and liquidity $L = \sqrt{xy}$. An LP wants to add $\Delta x$ of token X and $\Delta y$ of token Y.

There is a core constraint for adding liquidity: **adding liquidity must not change the asset price**. Liquidity providers are simply injecting more funds into the pool and should not alter the relative price of the tokens. Since price is defined by the reserve ratio, the price must be equal before and after adding liquidity:

$$\frac{y}{x} = \frac{y + \Delta y}{x + \Delta x} = P$$

This means the quantities of the two new tokens must be proportional to the current price:

$$\frac{\Delta y}{\Delta x} = \frac{y}{x} = P$$

That is, $\Delta y = \Delta x \cdot P$. The LP cannot freely choose the quantities of the two tokens to provide; they must strictly follow the current price ratio.

### Calculating the Liquidity Increment

Since $\Delta x$ and $\Delta y$ satisfy the price constraint, their product is also a constant. We denote the liquidity increment as $\Delta L$. It can be shown that:

$$\Delta L = \Delta x \cdot \sqrt{P} = \Delta x \cdot \sqrt{\frac{y}{x}} = L \cdot \frac{\Delta x}{x}$$

Similarly:

$$\Delta L = \frac{\Delta y}{\sqrt{P}} = L \cdot \frac{\Delta y}{y}$$

These two equations show: **the liquidity increment is proportional to the amount of tokens the LP provides, with the proportionality factor being the ratio of current liquidity to the corresponding token's reserves**. For example, if the LP provides token X equal to 1% of current reserves, the liquidity increment is also 1% of current liquidity.

After adding liquidity, the new liquidity is $L' = L + \Delta L$, satisfying:

$$L'^2 = (x + \Delta x)(y + \Delta y) = (L + \Delta L)^2$$

### Removing Liquidity

Removing liquidity is the reverse operation of adding liquidity. LPs withdraw both tokens in proportion to their liquidity share:

$$\Delta x = \frac{\Delta L}{L} \cdot x$$

$$\Delta y = \frac{\Delta L}{L} \cdot y$$

where $x$ and $y$ are the token reserves in the pool at the time of removal.

Notably, the $\Delta x$ and $\Delta y$ that an LP receives often differ from the amounts originally provided when adding liquidity — because the pool's token ratio may have changed due to trades in the interim. This is the fundamental cause of **impermanent loss**, which we analyze in detail in the next section.

## Impermanent Loss

### What is Impermanent Loss

When a liquidity provider deposits funds into an AMM pool, if the relative price of the tokens in the pool changes, the LP's asset value will be lower than the value of "simply holding" (i.e., doing nothing and keeping the tokens in a wallet). This difference is **impermanent loss** (IL).

It's called "impermanent" because if the price returns to the level at deposit time, the loss disappears. However, in practice, prices often don't return to the starting point, so the name "impermanent loss" can be misleading — a more accurate description would be **"a temporary paper loss that may well become permanent."**

### Mathematical Derivation

Suppose an LP deposits equal-value ETH and USDC into an ETH/USDC pool. The price at deposit is $P_0$, and the price later becomes $P$. Define the price change ratio:

$$r = \frac{P}{P_0}$$

When $r = 1$, the price is unchanged; $r > 1$ means ETH has appreciated; $r < 1$ means ETH has depreciated.

**Step 1: Calculate the LP's asset value in the pool**

Suppose at the initial deposit, the pool has $x$ ETH and $y$ USDC, with $P_0 = y/x$. From the constant product constraint $x \cdot y = k$, and given that $x \cdot P_0 = y$ (equal-value deposit), we get $x = \sqrt{k/P_0}$ and $y = \sqrt{k \cdot P_0}$.

When the price changes to $P$, the pool's assets rebalance to:

$$x' = \sqrt{\frac{k}{P}}, \quad y' = \sqrt{k \cdot P}$$

The LP's total asset value in the pool (denominated in USDC):

$$V_{\text{pool}} = x' \cdot P + y' = \sqrt{\frac{k}{P}} \cdot P + \sqrt{k \cdot P} = \sqrt{kP} + \sqrt{kP} = 2\sqrt{kP}$$

**Step 2: Calculate the value of simply holding**

The LP's initial ETH and USDC holdings, also denominated in USDC:

$$V_{\text{hold}} = x \cdot P + y = \sqrt{\frac{k}{P_0}} \cdot P + \sqrt{kP_0} = \sqrt{k} \left(\frac{P}{\sqrt{P_0}} + \sqrt{P_0}\right) = \sqrt{kP_0}\left(r + 1\right)$$

**Step 3: Calculate impermanent loss**

Comparing the two:

$$\frac{V_{\text{pool}}}{V_{\text{hold}}} = \frac{2\sqrt{kP}}{\sqrt{kP_0}(r + 1)} = \frac{2\sqrt{r}}{r + 1}$$

Therefore, the impermanent loss ratio is:

$$\text{IL} = 1 - \frac{2\sqrt{r}}{r + 1}$$

### Key Conclusions

Let's plug in some specific price change ratios $r$ to get a feel for the magnitude of impermanent loss:

| Price Change | $r$ | $V_{\text{pool}} / V_{\text{hold}}$ | Impermanent Loss |
|---------|-----|-------------------------------------|---------|
| No change | 1.00 | 100.00% | 0.00% |
| ±25% | 1.25 | 99.01% | 0.99% |
| ±50% | 1.50 | 97.98% | 2.02% |
| ±100% | 2.00 | 94.28% | 5.72% |
| ±200% | 3.00 | 86.60% | 13.40% |
| ±400% | 5.00 | 74.53% | 25.47% |

> **About Price Changes**
> The "±" in the table indicates: ETH appreciating by 25% ($r=1.25$) and ETH depreciating by 20% ($r=0.8$) result in the same impermanent loss. This is because the formula is symmetric in $r$ and $1/r$ — $\frac{2\sqrt{r}}{r+1}$ has the same value at $r$ and $1/r$. In other words, **price deviation in any direction causes impermanent loss, and the larger the deviation, the greater the loss**.

### Intuitive Explanation

Why does price change cause impermanent loss?

**The fundamental reason is that AMMs "sell" appreciating assets and "buy" depreciating assets when prices change**, which is the opposite of an investor's ideal behavior (hold appreciating assets, sell depreciating assets).

Specifically:
- When ETH's price rises, arbitrageurs continuously use USDC to buy ETH from the pool. The pool's ETH decreases and USDC increases. LPs are "forced to sell" the appreciating ETH
- When ETH's price falls, arbitrageurs continuously use ETH to swap for USDC from the pool. The pool's ETH increases and USDC decreases. LPs are "forced to buy" the depreciating ETH

This "passive rebalancing" is an inherent property of CPMM and the root cause of impermanent loss.

### Balancing Impermanent Loss and Fees

Impermanent loss may sound alarming, but in reality, LPs also earn **trading fee revenue**. In Uniswap V2, for example, each trade incurs a 0.3% fee, all of which goes to LPs.

LP's net return = fee revenue - impermanent loss

- When fee revenue > impermanent loss, the LP earns a positive return
- When fee revenue < impermanent loss, the LP has a net loss

Therefore, **whether an LP is profitable depends on the pool's trading activity and price volatility**: more active trading generates more fee revenue; greater price volatility leads to larger impermanent losses.

## Summary

- **Market makers**: Provide liquidity to the market by continuously offering buy and sell quotes, earning the bid-ask spread
- **Order book model and on-chain dilemma**: The order book model works well in centralized exchanges but faces fundamental challenges on-chain such as high gas costs and liquidity fragmentation
- **AMM**: Uses mathematical formulas and liquidity pools to replace order books and traditional market makers. Multiple AMM models exist (CPMM, CSMM, CMMM, hybrid AMMs), among which the constant product market maker is widely adopted for its simplicity and generality
- **Constant product (CPMM)**: $x \cdot y = k$ is the most classic AMM formula. The swap amount is determined by $\Delta y = \frac{\Delta x \cdot y}{x + \Delta x}$. The price is implicitly determined by the reserve ratio $y/x$
- **Slippage and price impact**: The larger the trade, the more the effective exchange rate deviates from the marginal price. The more funds in the pool (the larger $k$), the less slippage for the same trade size
- **Liquidity management**: Liquidity $L = \sqrt{xy}$. Adding liquidity does not change the price; new tokens must follow the proportional constraint $\Delta y / \Delta x = y/x = P$. The liquidity increment $\Delta L = L \cdot \Delta x / x$
- **Impermanent loss**: The loss LPs face due to the AMM's passive rebalancing mechanism. The formula is $\text{IL} = 1 - \frac{2\sqrt{r}}{r+1}$. The larger the price deviation, the greater the loss. An LP's actual return depends on the balance between fee revenue and impermanent loss

## References

- [Ethereum.org: Automated Market Makers (AMMs)](https://ethereum.org/en/developers/docs/defi/automated-market-makers/)
- [Uniswap V2 Whitepaper](https://uniswap.org/whitepaper.pdf) — Hayden Adams, Noah Zinsmeister, Dan Robinson, 2020
- [Uniswap V3 Whitepaper](https://uniswap.org/whitepaper-v3.pdf) — Hayden Adams, Noah Zinsmeister, Dan Robinson, 2021
- [Balancer Whitepaper](https://balancer.fi/whitepaper.pdf) — Fernando Martinelli, Nikolai Mushegian, 2019
- [Curve Whitepaper](https://curve.fi/curve%20DAO.pdf) — Michael Egorov, 2019
- [Improving Front Running Resistance of X*y=k Market Makers](https://arxiv.org/abs/2007.12272) — Guillermo Angeris, Tarun Chitra, Alex Evans, Stephen Boyd, 2020
- [An analysis of Uniswap markets](https://arxiv.org/abs/1911.03380) — Guillermo Angeris, Hsien-Tang Kao, Rei Chiang, Charlie Noyes, Tarun Chitra, 2019

> **Reading Note**
> This chapter establishes a purely theoretical mathematical framework. Starting from the next chapter, we will first learn about the fundamental tool for on-chain computation — fixed-point arithmetic — and then dive into Uniswap's contract source code to see how these theories are translated into Solidity implementations.
