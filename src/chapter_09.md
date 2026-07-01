# The Router Contract

The Router is the main entry point for users to interact with Uniswap V2. It does not perform swap math itself; instead, building on the previous chapter's libraries, it encapsulates the workflow of "preparing tokens, calling the Pair, and validating the result" into a set of user-facing interfaces: adding and removing liquidity, single- and multi-hop swaps, and native ETH wrapping, layered with the slippage protection and deadline checks that the core layer deliberately omits. This chapter steps into the implementation of `UniswapV2Router01` and `UniswapV2Router02`, seeing how they weave disparate Pair operations into a complete user-interaction experience.

## State and Constructor

The skeleton of both Routers is identical. The constructor binds two immutable addresses around which the entire contract revolves:

```solidity
// v2-periphery/contracts/UniswapV2Router02.sol

address public immutable override factory;
address public immutable override WETH;

constructor(address _factory, address _WETH) public {
    factory = _factory;
    WETH = _WETH;
}

receive() external payable {
    assert(msg.sender == WETH); // only accept ETH via fallback from the WETH contract
}
```

`factory` is the core-layer Factory, through which the Router creates trading pairs; `WETH` is the _Wrapped Ether (WETH)_ contract. Native ETH is not an ERC20 — it has no `balanceOf`/`transfer` methods — and Pairs only accept ERC20, so they cannot hold ETH directly. WETH is ETH's ERC20 wrapper: `deposit()` takes ETH and mints WETH 1:1; `withdraw()` burns WETH and releases an equivalent amount of ETH. The Router performs this wrapping/unwrapping at both ends of a swap, letting users participate with native ETH while Pairs always handle only WETH.

`receive()` accepts ETH only from WETH: when the Router calls `WETH.withdraw()`, the WETH contract transfers ETH back, triggering this fallback function to receive it. `assert(msg.sender == WETH)` ensures only this unwrapping path can inject ETH into the Router, ruling out unexpected deposits from any other source.

### Deadline Check: ensure

```solidity
modifier ensure(uint deadline) {
    require(deadline >= block.timestamp, 'UniswapV2Router: EXPIRED');
    _;
}
```

`ensure` is a modifier carried by nearly every external function, implementing the _deadline check_: the transaction must be mined no later than `deadline`, or it reverts. It targets the "transaction stalling" risk: after a user signs a transaction, it may be delayed by miners for a long time due to congestion; if the price has moved significantly by then, an originally reasonable swap would execute at a stale price. The user sets `deadline = current time + tolerance` (e.g., 20 minutes) at submission; if expired, it is voided, forcing the user to re-evaluate.

## Adding Liquidity

### Ratio Computation: _addLiquidity

`_addLiquidity` is the core of adding liquidity, responsible for converting "how much the user wants to deposit" into "how much should be deposited at the pool's price," with slippage protection:

```solidity
function _addLiquidity(
    address tokenA, address tokenB,
    uint amountADesired, uint amountBDesired,
    uint amountAMin, uint amountBMin
) internal virtual returns (uint amountA, uint amountB) {
    // create the pair if it doesn't exist yet
    if (IUniswapV2Factory(factory).getPair(tokenA, tokenB) == address(0)) {
        IUniswapV2Factory(factory).createPair(tokenA, tokenB);
    }
    (uint reserveA, uint reserveB) = UniswapV2Library.getReserves(factory, tokenA, tokenB);
    if (reserveA == 0 && reserveB == 0) {
        (amountA, amountB) = (amountADesired, amountBDesired);
    } else {
        uint amountBOptimal = UniswapV2Library.quote(amountADesired, reserveA, reserveB);
        if (amountBOptimal <= amountBDesired) {
            require(amountBOptimal >= amountBMin, 'UniswapV2Router: INSUFFICIENT_B_AMOUNT');
            (amountA, amountB) = (amountADesired, amountBOptimal);
        } else {
            uint amountAOptimal = UniswapV2Library.quote(amountBDesired, reserveB, reserveA);
            assert(amountAOptimal <= amountADesired);
            require(amountAOptimal >= amountAMin, 'UniswapV2Router: INSUFFICIENT_A_AMOUNT');
            (amountA, amountB) = (amountAOptimal, amountBDesired);
        }
    }
}
```

The logic falls into three cases. First, if the pair does not yet exist, the Router first calls the Factory's `createPair` to create it (one of the few operations where the Router modifies core-layer state). Second, if the pool has no reserves yet, the two tokens the user provides serve directly as the initial ratio `(amountADesired, amountBDesired)`, since there is no historical price to reference at this point. Third, when the pool already has reserves, it uses Chapter 8's `quote` to compute the "optimal" quantity of B from `amountADesired`, yielding `amountBOptimal`:

- If `amountBOptimal <= amountBDesired`, the user has provided enough B (perhaps even a surplus); deposit `amountADesired` in full and take the optimal amount of B.
- Otherwise, the user has not provided enough B to balance `amountADesired`; reverse the approach and deposit `amountBDesired` in full, computing the optimal amount of A.

In either case, the "proportionally optimal amount" is paired; the surplus of the other token is effectively donated to the pool (benefiting existing LPs). `amountAMin`/`amountBMin` are the slippage protection: if the actual deposit amount computed falls below the user-set lower bound (indicating the pool price has moved since submission), the transaction reverts.

### addLiquidity and addLiquidityETH

`_addLiquidity` only computes quantities; the actual transfer and minting happen in the outer function:

```solidity
function addLiquidity(...) external virtual override ensure(deadline)
    returns (uint amountA, uint amountB, uint liquidity)
{
    (amountA, amountB) = _addLiquidity(tokenA, tokenB, amountADesired, amountBDesired, amountAMin, amountBMin);
    address pair = UniswapV2Library.pairFor(factory, tokenA, tokenB);
    TransferHelper.safeTransferFrom(tokenA, msg.sender, pair, amountA);
    TransferHelper.safeTransferFrom(tokenB, msg.sender, pair, amountB);
    liquidity = IUniswapV2Pair(pair).mint(to);
}
```

This is the realization of Chapter 7's `mint` "transfer-first-then-mint" calling convention: the Router uses `TransferHelper.safeTransferFrom` (from `@uniswap/lib`, a safe transfer wrapper with return-value checking) to transfer both tokens from the user into the Pair, then calls `pair.mint(to)`, and the Pair mints LP Tokens based on the balance difference. `pairFor` computes the Pair address directly, without first querying the Factory.

`addLiquidityETH` is its ETH variant: it treats WETH as one of the tokens, using `msg.value` as the ETH amount. It first `transferFrom`s the other token, then `WETH.deposit{value: amountETH}()` to wrap ETH into WETH and transfer it into the Pair, and finally `mint`s. If the user sent excess ETH (`msg.value > amountETH`), the difference is refunded:

```solidity
IWETH(WETH).deposit{value: amountETH}();
assert(IWETH(WETH).transfer(pair, amountETH));
liquidity = IUniswapV2Pair(pair).mint(to);
if (msg.value > amountETH) TransferHelper.safeTransferETH(msg.sender, msg.value - amountETH);
```

## Removing Liquidity

### removeLiquidity and removeLiquidityETH

```solidity
function removeLiquidity(...) public virtual override ensure(deadline) returns (uint amountA, uint amountB) {
    address pair = UniswapV2Library.pairFor(factory, tokenA, tokenB);
    IUniswapV2Pair(pair).transferFrom(msg.sender, pair, liquidity); // send liquidity to pair
    (uint amount0, uint amount1) = IUniswapV2Pair(pair).burn(to);
    (address token0,) = UniswapV2Library.sortTokens(tokenA, tokenB);
    (amountA, amountB) = tokenA == token0 ? (amount0, amount1) : (amount1, amount0);
    require(amountA >= amountAMin, 'UniswapV2Router: INSUFFICIENT_A_AMOUNT');
    require(amountB >= amountBMin, 'UniswapV2Router: INSUFFICIENT_B_AMOUNT');
}
```

Removal is the inverse of addition, following `burn`'s "first transfer LP Tokens into the Pair, then call burn" convention (Chapter 7): the Router uses `transferFrom` to move the user's LP Tokens into the Pair, then calls `pair.burn(to)` to withdraw both tokens. The `(amount0, amount1)` returned by `burn` is sorted by `token0`/`token1`; here `sortTokens` restores it to the `(A, B)` order the user expects, and slippage checks are applied.

`removeLiquidityETH` reuses `removeLiquidity`: it first withdraws the WETH along with the other token back to the Router itself (`to = address(this)`), then `safeTransfer`s the token out and `WETH.withdraw`s the WETH into ETH, finally `safeTransferETH`-ing it to the user.

### permit Integration: The WithPermit Variants

Removing liquidity requires first authorizing the Router for the LP Tokens. The conventional flow requires the user to first send a separate `approve` transaction, then a `removeLiquidity` transaction — two in total. Variants like `removeLiquidityWithPermit` use Chapter 4's EIP-2612 permit to combine the two steps:

```solidity
function removeLiquidityWithPermit(...) external virtual override returns (uint amountA, uint amountB) {
    address pair = UniswapV2Library.pairFor(factory, tokenA, tokenB);
    uint value = approveMax ? uint(-1) : liquidity;
    IUniswapV2Pair(pair).permit(msg.sender, address(this), value, deadline, v, r, s);
    (amountA, amountB) = removeLiquidity(tokenA, tokenB, liquidity, amountAMin, amountBMin, to, deadline);
}
```

The user authorizes the Router to operate their LP Tokens with an off-chain signature; within the same transaction, the Router first calls `permit` to complete the authorization (via signature, with no prior `approve` needed), then executes `removeLiquidity`. `approveMax` determines whether the authorized amount is the maximum (`uint(-1)`, paired with Chapter 4's infinite-allowance skip) or exactly the `liquidity` for this operation.

## Swapping and Multi-hop Routing

### Multi-hop Execution: _swap

The core of swapping is the internal function `_swap`, which calls each Pair's `swap` hop by hop along a path:

```solidity
function _swap(uint[] memory amounts, address[] memory path, address _to) internal virtual {
    for (uint i; i < path.length - 1; i++) {
        (address input, address output) = (path[i], path[i + 1]);
        (address token0,) = UniswapV2Library.sortTokens(input, output);
        uint amountOut = amounts[i + 1];
        (uint amount0Out, uint amount1Out) = input == token0 ? (uint(0), amountOut) : (amountOut, uint(0));
        address to = i < path.length - 2 ? UniswapV2Library.pairFor(factory, output, path[i + 2]) : _to;
        IUniswapV2Pair(UniswapV2Library.pairFor(factory, input, output)).swap(amount0Out, amount1Out, to, new bytes(0));
    }
}
```

Each hop `(path[i], path[i+1])` corresponds to a Pair. `amounts` is the per-hop output pre-computed by the previous chapter's `getAmountsOut`/`getAmountsIn`; `amounts[i+1]` is this hop's output. `sortTokens` determines whether the input token is `token0` or `token1`, placing the output amount on `amount0Out` or `amount1Out` accordingly (Chapter 7's `swap` determines direction by the non-zero entry of these two parameters).

The key linkage is `to`: intermediate hops' output is not sent to the user but to **the next hop's Pair**; `pairFor(factory, output, path[i+2])` counterfactually computes the next Pair's address, so this hop's output tokens directly become the next hop's input; only the last hop sends the result to the user `_to`. `new bytes(0)` indicates no flash swap callback (Chapter 7) — it is an ordinary swap. This way, a path like `[A, B, C]` is compressed into a single transaction: the output of A→B is fed in place to B→C, with no need for the user to perform multiple separate operations.

### exact-input and exact-output

The Router divides swaps into "exact input" and "exact output" categories, each with token/ETH variants. Taking `swapExactTokensForTokens` (exact input) as an example:

```solidity
function swapExactTokensForTokens(uint amountIn, uint amountOutMin, address[] calldata path, address to, uint deadline)
    external virtual override ensure(deadline) returns (uint[] memory amounts)
{
    amounts = UniswapV2Library.getAmountsOut(factory, amountIn, path);
    require(amounts[amounts.length - 1] >= amountOutMin, 'UniswapV2Router: INSUFFICIENT_OUTPUT_AMOUNT');
    TransferHelper.safeTransferFrom(path[0], msg.sender, UniswapV2Library.pairFor(factory, path[0], path[1]), amounts[0]);
    _swap(amounts, path, to);
}
```

Exact input: use `getAmountsOut` to compute each hop and the final output from the input, then apply slippage protection with `amountOutMin` (the actual output must not fall below the lower bound), and finally transfer the first hop's input into the first Pair and execute `_swap`. `swapTokensForExactTokens` (exact output) goes the other way: it uses `getAmountsIn` to back-compute how much input is needed from the desired final output, limits the input with `amountInMax`, and proceeds with the rest of the flow identically. This is exactly where the previous chapter's `getAmountsOut` (forward accumulation) and `getAmountsIn` (back-solving) come into play.

### ETH Wrapping and Unwrapping

The ETH variants place WETH at one end of the path, with the Router responsible for wrapping or unwrapping:

- **ETH for tokens** (`swapExactETHForTokens`, `swapETHForExactTokens`): the path begins with WETH. The Router first `WETH.deposit{value: ...}()` to wrap the user's ETH into WETH and transfer it into the first Pair, then `_swap`s, sending the output tokens to the user.
- **Tokens for ETH** (`swapExactTokensForETH`, `swapTokensForExactETH`): the path ends with WETH. `_swap`'s final `to` is set to the Router itself, so the output WETH lands in the Router's hands; the Router then `WETH.withdraw`s it into ETH and `safeTransferETH`s it to the user.

All ETH variants share a common requirement in path validation: `path[0] == WETH` (ETH for tokens) or `path[path.length-1] == WETH` (tokens for ETH), ensuring the wrapping/unwrapping happens at the correct endpoint. The exact-input ETH variants also refund any excess ETH sent (dust refund).

## Differences Between Router01 and Router02

`UniswapV2Router02` is not a rewrite but an enhanced version built on `Router01` (its interface `IUniswapV2Router02` inherits from `IUniswapV2Router01`). The differences are concentrated in three areas.

### Overridability

`Router01`'s `_addLiquidity` and `_swap` are `private`, and the external functions are not overridable either, so the contract cannot be customized through inheritance. `Router02` changes these two internal functions to `internal virtual` and adds `virtual` to all external functions, allowing projects to inherit `Router02` and override individual methods to extend behavior (e.g., inserting custom callback or routing logic) without copying the entire contract.

### Fee-on-Transfer Token Support

This is `Router02`'s most substantial addition. Ordinary swaps use `getAmountsOut` to estimate the output, but that function assumes "whatever is transferred in is received in full"; for fee-on-transfer tokens, each transfer deducts a fee, so the actual received amount is less than the transferred amount, and `getAmountsOut`'s estimate is too large — causing the swap to fail. `Router02` adds `_swapSupportingFeeOnTransferTokens` and five `*SupportingFeeOnTransferTokens` variants to handle such tokens:

```solidity
function _swapSupportingFeeOnTransferTokens(address[] memory path, address _to) internal virtual {
    for (uint i; i < path.length - 1; i++) {
        (address input, address output) = (path[i], path[i + 1]);
        (address token0,) = UniswapV2Library.sortTokens(input, output);
        IUniswapV2Pair pair = IUniswapV2Pair(UniswapV2Library.pairFor(factory, input, output));
        uint amountInput; uint amountOutput;
        {
            (uint reserve0, uint reserve1,) = pair.getReserves();
            (uint reserveInput, uint reserveOutput) = input == token0 ? (reserve0, reserve1) : (reserve1, reserve0);
            amountInput = IERC20(input).balanceOf(address(pair)).sub(reserveInput);
            amountOutput = UniswapV2Library.getAmountOut(amountInput, reserveInput, reserveOutput);
        }
        (uint amount0Out, uint amount1Out) = input == token0 ? (uint(0), amountOutput) : (amountOutput, uint(0));
        address to = i < path.length - 2 ? UniswapV2Library.pairFor(factory, output, path[i + 2]) : _to;
        pair.swap(amount0Out, amount1Out, to, new bytes(0));
    }
}
```

It no longer pre-estimates the entire path with `getAmountsOut`, but instead **measures hop by hop in real time**: this hop's input tokens have already been transferred into the Pair, so the Router directly reads the Pair's balance and uses "balance − reserve" to compute the actual received amount `amountInput` (the Chapter 7 balance-difference pattern), then uses the single-hop `getAmountOut` to compute this hop's output and `swap`s. Since the final output cannot be known in advance, the outer function switches to post-hoc validation, comparing the balance increment of the user's received token against `amountOutMin` and reverting if it falls short. These five variants cover the token↔ETH combinations for exact-input mode (exact-output mode is not provided because it requires precise estimation and is incompatible with fee-on-transfer tokens).

### The getAmountIn Bug Fix

`Router01`'s `getAmountIn`, exposed to frontends, had a copy-paste error: it internally mis-called the forward `getAmountOut`:

```solidity
// v2-periphery/contracts/UniswapV2Router01.sol (buggy)
function getAmountIn(uint amountOut, uint reserveIn, uint reserveOut) public pure override returns (uint amountIn) {
    return UniswapV2Library.getAmountOut(amountOut, reserveIn, reserveOut);  // should be getAmountIn
}
```

This would cause off-chain estimation for "exact output" to return an incorrect input amount. `Router02` fixed it to correctly call `UniswapV2Library.getAmountIn`. This is also one reason new projects should adopt `Router02` directly.

### Library Function Passthrough

Both Routers re-expose `UniswapV2Library`'s `quote`, `getAmountOut`, `getAmountIn`, `getAmountsOut`, and `getAmountsIn` as `public` functions (the first three `pure`, the last two `view`). This is not redundant: frontends and aggregators typically hold only the Router address, so by passing through these functions they can query quotes directly from the Router without each having to re-implement a set or find the library's address separately.

## Summary

The Router does not perform swap math itself; instead, it weaves "prepare tokens, call the Pair, validate" into a set of interfaces, layered with the safety and convenience the core layer omits. It binds the immutable `factory` and `WETH`: the former creates trading pairs on demand, and the latter lets the ERC20-only Pair indirectly handle native ETH. Adding liquidity is handled by `_addLiquidity`, which uses `quote` to compute the optimal ratio and applies minimum-value slippage protection; removing liquidity returns LP Tokens to withdraw tokens, with `WithPermit` variants using EIP-2612 to compress authorization and removal into one transaction. The core of swapping is `_swap`: it calls each Pair's `swap` hop by hop along the path, with intermediate hops' output sent directly to the next Pair, compressing a multi-hop swap into a single transaction; `Router02` further supports fee-on-transfer tokens and fixes the bug in `Router01` where `getAmountIn` mis-called `getAmountOut`. With this, both the periphery libraries and the Router contract have been covered: the core layer trades minimalism for trustworthiness, and the periphery layer, with the Router as its entry point, fills in all the protection and convenience users need.
