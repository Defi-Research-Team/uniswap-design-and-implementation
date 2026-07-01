# Periphery Libraries

This chapter focuses on three stateless libraries in the periphery layer: `UniswapV2Library`, which handles address derivation and amount-and-price estimation; `UniswapV2OracleLibrary`, which assists in reading oracle data; and `UniswapV2LiquidityMathLibrary`, used to estimate the value of an LP share. None of them holds any state and they perform pure computation (or only read on-chain data in `view` mode), so they can be reused without side effects by Routers, frontends, aggregators, and any third-party protocol.

## UniswapV2Library

`UniswapV2Library` is the most frequently called library in the periphery layer; nearly every Router operation goes through it to compute addresses, query reserves, and estimate swap amounts. It consists of seven functions, dissected below grouped by purpose.

### Sorting and Addresses: sortTokens and pairFor

```solidity
// v2-periphery/contracts/libraries/UniswapV2Library.sol

function sortTokens(address tokenA, address tokenB) internal pure returns (address token0, address token1) {
    require(tokenA != tokenB, 'UniswapV2Library: IDENTICAL_ADDRESSES');
    (token0, token1) = tokenA < tokenB ? (tokenA, tokenB) : (tokenB, tokenA);
    require(token0 != address(0), 'UniswapV2Library: ZERO_ADDRESS');
}
```

`sortTokens` normalizes two token addresses in any order into `(token0, token1)` (smaller first). It is exactly the mirror of the line `tokenA < tokenB ? ...` in the Factory's `createPair` from Chapter 7. The periphery must use the **exact same sorting rule** as the Factory, for two reasons:

- **Deterministic addresses**: when `pairFor` computes a Pair's address, the salt is `keccak256(token0 ‖ token1)`; only with consistent sorting will the computed salt and address match what the Factory used at deployment.
- **Reserve ordering**: the Pair internally stores reserves as `(reserve0, reserve1)` (sorted by `token0`/`token1`). `getReserves` must restore the result to the `(A, B)` order expected by the caller, which also depends on the same sorting.

```solidity
function pairFor(address factory, address tokenA, address tokenB) internal pure returns (address pair) {
    (address token0, address token1) = sortTokens(tokenA, tokenB);
    pair = address(uint(keccak256(abi.encodePacked(
            hex'ff',
            factory,
            keccak256(abi.encodePacked(token0, token1)),
            hex'96e8ac4277198ff8b6f785478aa9a39f403cb768dd02cbee326c3e7da348845f' // init code hash
        ))));
}
```

`pairFor` computes the Pair's address in place using the CREATE2 address formula (Chapter 7, Equation (1)) and the constant init code hash (constant (2)); its principle was covered in detail in Chapter 7. Here we only need to remember its value: a `pure` function with zero external calls that lets the periphery locate any Pair counterfactually without first querying the Factory.

### Reserve Query: getReserves

```solidity
function getReserves(address factory, address tokenA, address tokenB)
    internal view returns (uint reserveA, uint reserveB)
{
    (address token0,) = sortTokens(tokenA, tokenB);
    (uint reserve0, uint reserve1,) = IUniswapV2Pair(pairFor(factory, tokenA, tokenB)).getReserves();
    (reserveA, reserveB) = tokenA == token0 ? (reserve0, reserve1) : (reserve1, reserve0);
}
```

`getReserves` combines three steps into one — "compute address → read reserves → restore order": it first locates the Pair with `pairFor`, calls its `getReserves()` to get `(reserve0, reserve1)` sorted by `token0`/`token1`, then decides whether to swap them based on whether `tokenA` equals `token0`, thereby returning reserves **in the `(tokenA, tokenB)` order passed by the caller**. This way, the upper-layer code need not worry about sorting details — passing `(A, B)` yields `(reserveA, reserveB)`.

### Equivalent Amount: quote

```solidity
function quote(uint amountA, uint reserveA, uint reserveB) internal pure returns (uint amountB) {
    require(amountA > 0, 'UniswapV2Library: INSUFFICIENT_AMOUNT');
    require(reserveA > 0 && reserveB > 0, 'UniswapV2Library: INSUFFICIENT_LIQUIDITY');
    amountB = amountA.mul(reserveB) / reserveA;
}
```

`quote` computes the quantity of tokenB _equivalent_ to `amountA` of tokenA according to the current reserve ratio:

$$\text{amountB} = \text{amountA} \times \frac{\text{reserveB}}{\text{reserveA}} \tag{1}$$

It is purely a ratio of reserves — **no fee deduction, no price impact** — because it serves "proportional depositing" rather than "swapping." The next chapter's Router uses exactly this in `_addLiquidity` to compute: given a desired `amountADesired`, how much tokenB (`amountBOptimal`) should be paired according to the pool's price, and thereby judge whether the two tokens the user provided are proportional.

### Swap Amount Estimation: getAmountOut and getAmountIn

```solidity
function getAmountOut(uint amountIn, uint reserveIn, uint reserveOut) internal pure returns (uint amountOut) {
    require(amountIn > 0, 'UniswapV2Library: INSUFFICIENT_INPUT_AMOUNT');
    require(reserveIn > 0 && reserveOut > 0, 'UniswapV2Library: INSUFFICIENT_LIQUIDITY');
    uint amountInWithFee = amountIn.mul(997);
    uint numerator = amountInWithFee.mul(reserveOut);
    uint denominator = reserveIn.mul(1000).add(amountInWithFee);
    amountOut = numerator / denominator;
}
```

The formula for `getAmountOut` is Chapter 7, Equation (5), writing the 0.3% fee as $\frac{997}{1000}$: it first pre-deducts the fee from the input (`amountInWithFee = amountIn * 997`), then computes the output under the constant product, all using integer arithmetic to avoid floating point. It is an off-chain estimate; the Router uses it to compute the expected output, then relies on the on-chain `swap`'s K-invariant check (Chapter 7, Equation (3)) as a backstop.

`getAmountIn` is its inverse: given a desired output, it back-calculates how much input is needed. Solving the fee-bearing constant product $(x + 0.997\,\Delta x)(y - \Delta y) = x \cdot y$ for the input $\Delta x$:

$$\Delta x = \frac{x \cdot \Delta y}{0.997\,(y - \Delta y)} \tag{2}$$

After integerization ($0.997 = 997/1000$, multiply numerator and denominator by 1000), this becomes the code's formulation:

```solidity
function getAmountIn(uint amountOut, uint reserveIn, uint reserveOut) internal pure returns (uint amountIn) {
    require(amountOut > 0, 'UniswapV2Library: INSUFFICIENT_OUTPUT_AMOUNT');
    require(reserveIn > 0 && reserveOut > 0, 'UniswapV2Library: INSUFFICIENT_LIQUIDITY');
    uint numerator = reserveIn.mul(amountOut).mul(1000);
    uint denominator = reserveOut.sub(amountOut).mul(997);
    amountIn = (numerator / denominator).add(1);
}
```

Note the `.add(1)` at the end. Integer division rounds down, and in the "specified output amount" mode, the on-chain `swap`'s K check requires the actual received input to be **no less than** the theoretical value; if rounding down under-collects by a single wei, the check fails and the transaction reverts. So here it actively adds 1 to round up, ensuring the computed input is always sufficient.

### Multi-hop Chaining: getAmountsOut and getAmountsIn

Many token pairs have no direct trading pair, so a swap must go through an intermediate token, e.g., A → B → C. `UniswapV2Library` expresses such a path as an array of token addresses `path` (e.g., `[A, B, C]`), where adjacent entries form a hop, each hop corresponding to an independent Pair.

```solidity
function getAmountsOut(address factory, uint amountIn, address[] memory path)
    internal view returns (uint[] memory amounts)
{
    require(path.length >= 2, 'UniswapV2Library: INVALID_PATH');
    amounts = new uint[](path.length);
    amounts[0] = amountIn;
    for (uint i; i < path.length - 1; i++) {
        (uint reserveIn, uint reserveOut) = getReserves(factory, path[i], path[i + 1]);
        amounts[i + 1] = getAmountOut(amounts[i], reserveIn, reserveOut);
    }
}
```

`getAmountsOut` accumulates **forward** from beginning to end: `amounts[0]` is the initial input, each hop uses `getAmountOut` to compute the next hop's input, advancing segment by segment, and `amounts[last]` is the final output. `getAmountsIn` goes in the opposite direction:

```solidity
function getAmountsIn(address factory, uint amountOut, address[] memory path)
    internal view returns (uint[] memory amounts)
{
    require(path.length >= 2, 'UniswapV2Library: INVALID_PATH');
    amounts = new uint[](path.length);
    amounts[amounts.length - 1] = amountOut;
    for (uint i = path.length - 1; i > 0; i--) {
        (uint reserveIn, uint reserveOut) = getReserves(factory, path[i - 1], path[i]);
        amounts[i - 1] = getAmountIn(amounts[i], reserveIn, reserveOut);
    }
}
```

It **back-solves** starting from the desired final output `amountOut`: `amounts[last]` is the target output, and going backward it uses `getAmountIn` to compute hop by hop the output required of the previous hop (which is this hop's input); `amounts[0]` is the total that must be invested initially. Both decompose the multi-hop problem into a series of single hops: each hop independently queries its own reserves and applies the single-hop formula; the multi-hop merely chains the results together.

## UniswapV2OracleLibrary

Chapter 6 pointed out that the Pair is only responsible for accumulating "price × duration" into `price0CumulativeLast`/`price1CumulativeLast`, and that TWAP computation is delegated to external readers. `UniswapV2OracleLibrary` is the helper provided for these readers; its core is `currentCumulativePrices`.

### Counterfactual Cumulative Prices: currentCumulativePrices

```solidity
// v2-periphery/contracts/libraries/UniswapV2OracleLibrary.sol

function currentCumulativePrices(address pair)
    internal view returns (uint price0Cumulative, uint price1Cumulative, uint32 blockTimestamp)
{
    blockTimestamp = currentBlockTimestamp();
    price0Cumulative = IUniswapV2Pair(pair).price0CumulativeLast();
    price1Cumulative = IUniswapV2Pair(pair).price1CumulativeLast();

    // if time has elapsed since the last update on the pair, mock the accumulated price values
    (uint112 reserve0, uint112 reserve1, uint32 blockTimestampLast) = IUniswapV2Pair(pair).getReserves();
    if (blockTimestampLast != blockTimestamp) {
        // subtraction overflow is desired
        uint32 timeElapsed = blockTimestamp - blockTimestampLast;
        // addition overflow is desired
        price0Cumulative += uint(FixedPoint.fraction(reserve1, reserve0)._x) * timeElapsed;
        price1Cumulative += uint(FixedPoint.fraction(reserve0, reserve1)._x) * timeElapsed;
    }
}
```

To understand this code, first recall the Pair's accumulation timing: `price0CumulativeLast` is updated only once per block, on the **first** reserve change (i.e., in `_update`). So when you read it at an arbitrary moment, you often get the value as of "the last `_update` moment"; the time elapsed since then has not yet been accounted for, and the accumulator is "stale."

`currentCumulativePrices` addresses exactly this lag. It first reads the on-chain `price0CumulativeLast`; if it finds `blockTimestampLast != blockTimestamp` (i.e., some time has passed since the last update), it **computes in place** the not-yet-accumulated portion: it computes the price from the current reserves (`FixedPoint.fraction(reserve1, reserve0)` is equivalent to Chapter 6's `UQ112x112.encode(reserve1).uqdiv(reserve0)`), multiplies it by the elapsed time `timeElapsed`, and adds it to a local copy.

This is a _counterfactual_ computation: it does not call `sync` to actually update the on-chain state (which would change reserves, consume Gas, and potentially interfere with other logic), but instead "assumes an update just happened" and computes the value the accumulator **would** have. For an oracle that only needs to read the TWAP, this read-only "hypothetical value" suffices. The function is `view`; the two subtraction/addition overflows are, as inside the Pair, intentional unsigned wrapping (Chapter 6). `FixedPoint`, and the `Babylonian`/`FullMath` below, all come from Uniswap's shared library `@uniswap/lib` — general-purpose numeric tools outside the core layer.

## UniswapV2LiquidityMathLibrary

The first two libraries serve "swapping and reading"; `UniswapV2LiquidityMathLibrary` serves "valuation": given a unit of LP share, how much underlying token is it worth? The difficulty is that the pool's spot reserves can be instantaneously manipulated by a single large trade, so valuing directly from spot reserves would be exploitable by a _sandwich attack_. This library provides two valuation paths: one reads spot directly (cheap but manipulable), and the other assumes arbitrage has already pulled the price back to the "true price" (manipulation-resistant).

### Profit-Maximizing Trade: computeProfitMaximizingTrade and getReservesAfterArbitrage

```solidity
// v2-periphery/contracts/libraries/UniswapV2LiquidityMathLibrary.sol

function computeProfitMaximizingTrade(
    uint256 truePriceTokenA, uint256 truePriceTokenB,
    uint256 reserveA, uint256 reserveB
) pure internal returns (bool aToB, uint256 amountIn) {
    aToB = FullMath.mulDiv(reserveA, truePriceTokenB, reserveB) < truePriceTokenA;
    uint256 invariant = reserveA.mul(reserveB);
    uint256 leftSide = Babylonian.sqrt(
        FullMath.mulDiv(invariant.mul(1000), aToB ? truePriceTokenA : truePriceTokenB,
                        (aToB ? truePriceTokenB : truePriceTokenA).mul(997))
    );
    uint256 rightSide = (aToB ? reserveA.mul(1000) : reserveB.mul(1000)) / 997;
    if (leftSide < rightSide) return (false, 0);
    amountIn = leftSide.sub(rightSide);
}
```

`computeProfitMaximizingTrade` takes a pair of "true prices" `(truePriceTokenA : truePriceTokenB)` (i.e., a trusted external price ratio of A to B) and the pool's spot reserves, and computes the direction and size of the _profit-maximizing trade_ that moves the pool's price **exactly to the true price**.

The direction is determined by the first line: it compares the pool's implied price of A (`reserveB/reserveA`, in terms of B) with the true price (`truePriceA/truePriceB`). If A is overpriced in the pool, it sells A into the pool (`aToB = true`); otherwise it buys A. The size is solved by requiring "the pool price after this trade equals the true price"; the code implements this exactly with integers using `Babylonian.sqrt` (square root) and `FullMath.mulDiv` (512-bit full-precision multiply-divide). The core idea is: an arbitrageur will keep trading until the pool price and the true price leave no arbitrage gap; the reserves at that point are the "de-manipulated" fair reserves.

`getReservesAfterArbitrage` reads the spot reserves, calls the above to compute the arbitrage trade, then applies the trade's effect to the reserves using `UniswapV2Library.getAmountOut`, returning the post-arbitrage `(reserveA, reserveB)`.

### LP Share Valuation: getLiquidityValue and getLiquidityValueAfterArbitrageToPrice

```solidity
function computeLiquidityValue(
    uint256 reservesA, uint256 reservesB, uint256 totalSupply,
    uint256 liquidityAmount, bool feeOn, uint kLast
) internal pure returns (uint256 tokenAAmount, uint256 tokenBAmount) {
    if (feeOn && kLast > 0) {
        uint rootK = Babylonian.sqrt(reservesA.mul(reservesB));
        uint rootKLast = Babylonian.sqrt(kLast);
        if (rootK > rootKLast) {
            uint numerator1 = totalSupply;
            uint numerator2 = rootK.sub(rootKLast);
            uint denominator = rootK.mul(5).add(rootKLast);
            uint feeLiquidity = FullMath.mulDiv(numerator1, numerator2, denominator);
            totalSupply = totalSupply.add(feeLiquidity);
        }
    }
    return (reservesA.mul(liquidityAmount) / totalSupply, reservesB.mul(liquidityAmount) / totalSupply);
}
```

`computeLiquidityValue` is the valuation kernel. An LP share corresponds proportionally to the assets in the pool:

$$\text{tokenAAmount} = \text{reserveA} \times \frac{\text{liquidityAmount}}{\text{totalSupply}}$$

There is one subtlety: if the protocol fee is enabled (Chapter 5), the Pair's protocol fee accumulated since the last settlement has not yet been minted as LP Tokens, so `totalSupply` is understated. Here the Chapter 5, Equation (13) protocol fee minting formula is used (the `5` in the denominator is the trace of the $1/6$ sub-fee rate) to compute the pending `feeLiquidity`, which is added to `totalSupply` as a correction, so that the valuation is not distorted by this "implicit dilution."

`getLiquidityValue` reads the spot reserves and parameters directly and calls `computeLiquidityValue`. The source comments explicitly warn: **it can be manipulated by sandwich attacks** — an attacker can instantaneously push up the spot reserves and then withdraw, making the valuation briefly inflated. Therefore, `getLiquidityValueAfterArbitrageToPrice` is the more robust choice: it takes a trusted true price, first computes the "post-arbitrage" fair reserves via `getReservesAfterArbitrage`, then values. Since any manipulation of the spot reserves would be quickly erased by arbitrageurs pulling the price back to the true price, the attacker cannot profit from the inflated spot, and the valuation becomes manipulation-resistant. The cost is that a trusted external price must be supplied.

## Summary

`UniswapV2Library` is the backbone of the periphery layer: `sortTokens` is consistent with the Factory's sorting rule, establishing the foundation for deterministic addresses and reserve ordering; `pairFor` lets the periphery counterfactually compute a Pair's address with zero external calls; `getReserves` combines computing the address, reading reserves, and restoring order into one; `quote` gives the equivalent amount by the reserve ratio; `getAmountOut`/`getAmountIn` are forward and inverse swap estimates with the 0.3% fee, and `getAmountsOut`/`getAmountsIn` decompose a multi-hop swap into a chain of single hops accumulated separately. `UniswapV2OracleLibrary` uses counterfactual computation to make up the "price × duration" not yet accounted for by the Pair's accumulators — a read-side helper for building TWAP oracles. `UniswapV2LiquidityMathLibrary` serves LP share valuation: it first computes the arbitrage trade that moves the pool price to the true price to obtain de-manipulated fair reserves, then values proportionally and corrects for pending protocol fees; the spot-reading `getLiquidityValue` is vulnerable to sandwich manipulation, while `getLiquidityValueAfterArbitrageToPrice` is manipulation-resistant because it assumes arbitrage has already occurred, at the cost of requiring a trusted external price.
