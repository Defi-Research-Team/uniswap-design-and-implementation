# 路由合约

Router 是用户与 Uniswap V2 交互的主入口。它本身不做兑换数学，而是在上章工具库的基础上，把“准备好代币、调用 Pair、校验结果”这套流程封装成一组面向用户的接口：添加与移除流动性、单跳与多跳兑换、原生 ETH 的包装，并叠加核心层刻意省去的滑点保护与 deadline 检查。本章走进 `UniswapV2Router01` 与 `UniswapV2Router02` 的实现，看它们如何把零散的 Pair 操作编织成完整的用户交互。

## 状态与构造

两个 Router 的骨架完全一致。构造函数绑定两个不可变地址，整个合约围绕它们运转：

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

`factory` 是核心层的 Factory，Router 通过它创建交易对；`WETH` 是 _包装以太坊（Wrapped Ether, WETH）_ 合约。原生 ETH 不是 ERC20，没有 `balanceOf`/`transfer` 等方法，而 Pair 只认 ERC20，无法直接持有 ETH。WETH 正是 ETH 的 ERC20 包装：`deposit()` 存入 ETH、按 1:1 铸造 WETH，`withdraw()` 销毁 WETH、释放等额 ETH。Router 在兑换两端做这层包装/解包，让用户能用原生 ETH 参与，而 Pair 始终只处理 WETH。

`receive()` 只接受来自 WETH 的 ETH：当 Router 调用 `WETH.withdraw()` 时，WETH 合约会把 ETH 转回，触发此回退函数收款。`assert(msg.sender == WETH)` 确保只有这条解包路径能向 Router 注入 ETH，杜绝其它来源的意外打款。

### deadline 检查：ensure

```solidity
modifier ensure(uint deadline) {
    require(deadline >= block.timestamp, 'UniswapV2Router: EXPIRED');
    _;
}
```

`ensure` 是几乎每个外部函数都带的修饰器，实现 _deadline 检查_：交易必须在不晚于 `deadline` 的时刻打包，否则回滚。它针对的是“交易滞留”风险，用户签好一笔交易后，它可能因拥堵被矿工推迟很久才上链；若届时价格已大幅变动，原本合理的兑换会按过时价格成交。用户在提交时设 `deadline = 当前时间 + 容忍度`（如 20 分钟），过期即作废，迫使用户重新评估。

## 添加流动性

### 配比计算：_addLiquidity

`_addLiquidity` 是添加流动性的核心，负责把用户“想存多少”换算成“按池中价格应存多少”，并做滑点保护：

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

逻辑分三种情形。其一，若该交易对尚不存在，Router 先调 Factory 的 `createPair` 创建它（这是 Router 少数会改动核心层状态的操作）。其二，若池子还没有任何储备量，用户提供的两种代币直接作为初始比例 `(amountADesired, amountBDesired)`，因为这时没有任何历史价格可供参照。其三，池子已有储备量时，用第 8 章的 `quote` 按 `amountADesired` 算出“最优”的 B 数量 `amountBOptimal`：

- 若 `amountBOptimal <= amountBDesired`，说明用户给的 B 足够（甚至偏多），按 `amountADesired` 全额存入、B 取最优量即可；
- 否则用户给的 B 不足以配平 `amountADesired`，反过来按 `amountBDesired` 全额存入、算出最优的 A。

无论哪种，都取“按比例算出的最优量”配对，多出来的那种代币等价于无偿留在池中（对既有 LP 有利）。`amountAMin`/`amountBMin` 是滑点保护：若算出的实际存入量低于用户设的下限（说明池价在提交后已变动），交易回滚。

### addLiquidity 与 addLiquidityETH

`_addLiquidity` 只算数量，真正的转账与铸造在外层函数：

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

这正是第 7 章 `mint` 的“先转账后铸造”调用约定的落地：Router 用 `TransferHelper.safeTransferFrom`（来自 `@uniswap/lib`，封装了带返回值检查的安全转账）把两种代币从用户转入 Pair，再调 `pair.mint(to)`，Pair 凭余额差铸造 LP Token。`pairFor` 直接算出 Pair 地址，无需先查询 Factory。

`addLiquidityETH` 是其 ETH 版本：把 WETH 当作其中一种代币，用 `msg.value` 作为 ETH 数量。它先 `transferFrom` 另一种代币，再 `WETH.deposit{value: amountETH}()` 把 ETH 包装成 WETH、转入 Pair，最后 `mint`。若用户多发了 ETH（`msg.value > amountETH`），差额退还：

```solidity
IWETH(WETH).deposit{value: amountETH}();
assert(IWETH(WETH).transfer(pair, amountETH));
liquidity = IUniswapV2Pair(pair).mint(to);
if (msg.value > amountETH) TransferHelper.safeTransferETH(msg.sender, msg.value - amountETH);
```

## 移除流动性

### removeLiquidity 与 removeLiquidityETH

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

移除是添加的逆过程，遵循 `burn` 的“先把 LP Token 转入 Pair、再调 burn”约定（第 7 章）：Router 用 `transferFrom` 把用户的 LP Token 转入 Pair，调 `pair.burn(to)` 取回两种代币。`burn` 返回的 `(amount0, amount1)` 按 `token0`/`token1` 排序，这里再用 `sortTokens` 还原成用户期望的 `(A, B)` 顺序，并做滑点校验。

`removeLiquidityETH` 复用 `removeLiquidity`：先把 WETH 连同另一种代币取回到 Router 自己（`to = address(this)`），再 `safeTransfer` 转出代币、`WETH.withdraw` 把 WETH 解包成 ETH、`safeTransferETH` 发给用户。

### permit 集成：WithPermit 变体

移除流动性需要先把 LP Token 授权给 Router。常规流程要求用户先单独发一笔 `approve` 交易，再发 `removeLiquidity` 交易，共两笔。`removeLiquidityWithPermit` 等变体利用第 4 章的 EIP-2612 permit，把两步合一：

```solidity
function removeLiquidityWithPermit(...) external virtual override returns (uint amountA, uint amountB) {
    address pair = UniswapV2Library.pairFor(factory, tokenA, tokenB);
    uint value = approveMax ? uint(-1) : liquidity;
    IUniswapV2Pair(pair).permit(msg.sender, address(this), value, deadline, v, r, s);
    (amountA, amountB) = removeLiquidity(tokenA, tokenB, liquidity, amountAMin, amountBMin, to, deadline);
}
```

用户用链下签名授权 Router 操作其 LP Token；Router 在同一笔交易里先调 `permit` 完成授权（凭签名，无需事先 `approve`），再执行 `removeLiquidity`。`approveMax` 决定授权额度是最大值（`uint(-1)`，配合第 4 章的无限授权跳过扣减）还是恰好本次的 `liquidity`。

## 兑换与多跳路由

### 多跳执行：_swap

兑换的核心是内部函数 `_swap`，它沿一条路径逐跳调用各 Pair 的 `swap`：

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

每一跳 `(path[i], path[i+1])` 对应一个 Pair。`amounts` 是上章 `getAmountsOut`/`getAmountsIn` 预先算好的各跳输出量，`amounts[i+1]` 即本跳的输出。`sortTokens` 判断输入代币是 `token0` 还是 `token1`，据此把输出量放到 `amount0Out` 或 `amount1Out` 上（第 7 章 `swap` 由这两个参数的非零项决定方向）。

关键的衔接在 `to`：中间各跳的输出不发给用户，而是发给**下一跳的 Pair**，`pairFor(factory, output, path[i+2])` 反事实地算出下一个 Pair 的地址，本跳的输出代币直接成为下一跳的输入；只有最后一跳才把结果发给用户 `_to`。`new bytes(0)` 表示不触发闪电兑换回调（第 7 章），是普通兑换。这样一条 `[A, B, C]` 路径就被压缩进一次交易：A→B 的输出原地喂给 B→C，用户无需分多笔操作。

### exact-input 与 exact-output

Router 把兑换分成“确定输入”与“确定输出”两类，每类又有代币/ETH 的变体。以 `swapExactTokensForTokens`（确定输入）为例：

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

确定输入：用 `getAmountsOut` 由输入算出各跳乃至最终输出，再用 `amountOutMin` 做滑点保护（实际输出不得低于下限），最后把首跳输入转入第一个 Pair 并执行 `_swap`。`swapTokensForExactTokens`（确定输出）则反过来：用 `getAmountsIn` 由期望的最终输出反推最初需要投入多少，用 `amountInMax` 限制投入上限，其余流程相同。这正是上章 `getAmountsOut`（正向累加）与 `getAmountsIn`（反向求解）的用武之地。

### ETH 的包装与解包

ETH 变体把 WETH 放在路径的某一端，由 Router 负责包装或解包：

- **ETH 换代币**（`swapExactETHForTokens`、`swapETHForExactTokens`）：路径以 WETH 开头。Router 先 `WETH.deposit{value: ...}()` 把用户发来的 ETH 包装成 WETH、转入第一个 Pair，再 `_swap`，输出代币发给用户。
- **代币换 ETH**（`swapExactTokensForETH`、`swapTokensForExactETH`）：路径以 WETH 结尾。`_swap` 的最终 `to` 设为 Router 自己，输出的 WETH 落在 Router 手中；Router 随即 `WETH.withdraw` 把它解包成 ETH，再 `safeTransferETH` 发给用户。

所有 ETH 变体在路径校验上都有一个共同要求：`path[0] == WETH`（ETH 换代币）或 `path[path.length-1] == WETH`（代币换 ETH），确保包装/解包发生在正确的端点。确定输入的 ETH 变体还会把多发的 ETH 退还（dust refund）。

## Router01 与 Router02 的差异

`UniswapV2Router02` 并非重写，而是在 `Router01` 基础上的增强版（其接口 `IUniswapV2Router02` 继承自 `IUniswapV2Router01`）。差异集中在三处。

### 可覆盖性

`Router01` 的 `_addLiquidity`、`_swap` 是 `private`，外部函数也不可覆盖，合约无法被继承定制。`Router02` 把这两个内部函数改为 `internal virtual`，所有外部函数也加了 `virtual`，使得项目可以继承 `Router02`、覆盖个别方法来扩展行为（例如插入自定义的回调或路由逻辑），而不必复制整个合约。

### 转账扣费代币支持

这是 `Router02` 最实质的新增。普通兑换用 `getAmountsOut` 预估输出，但该函数假定“转入多少就到账多少”；对于转账扣费代币，其每笔转账会扣走一部分费用，实际到账量少于转入量，`getAmountsOut` 的预估就会偏大、导致兑换失败。`Router02` 新增 `_swapSupportingFeeOnTransferTokens` 与五个 `*SupportingFeeOnTransferTokens` 变体来处理这类代币：

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

它不再预先用 `getAmountsOut` 估算整条路径，而是**逐跳实测**：本跳的输入代币已被转入 Pair，Router 直接读 Pair 的余额、用“余额 − 储备量”算出真实到账量 `amountInput`（第 7 章余额差模式），再用单跳 `getAmountOut` 算出本跳输出并 `swap`。由于无法预先知道最终输出，外层函数改为事后校验，比较用户接收代币的余额增量是否达到 `amountOutMin`，达不到则回滚。这五个变体分别覆盖“确定输入”的代币↔ETH 组合（确定输出模式因需精确预估、不兼容扣费代币，故未提供）。

### getAmountIn 的 bug 修复

`Router01` 暴露给前端的 `getAmountIn` 有一处复制粘贴错误，它内部误调了正向的 `getAmountOut`：

```solidity
// v2-periphery/contracts/UniswapV2Router01.sol（有 bug）
function getAmountIn(uint amountOut, uint reserveIn, uint reserveOut) public pure override returns (uint amountIn) {
    return UniswapV2Library.getAmountOut(amountOut, reserveIn, reserveOut);  // 应为 getAmountIn
}
```

这会让“确定输出”的链下估算返回错误的输入量。`Router02` 已修正为正确调用 `UniswapV2Library.getAmountIn`。这也正是新项目应直接采用 `Router02` 的原因之一。

### 库函数透传

两个 Router 都把 `UniswapV2Library` 的 `quote`、`getAmountOut`、`getAmountIn`、`getAmountsOut`、`getAmountsIn` 作为 `public` 函数重新暴露（前三个 `pure`、后两个 `view`）。这并非多此一举：前端与聚合器通常只持有 Router 地址，透传这些函数后，它们就能直接向 Router 查询报价，而不必各自再实现一套或另寻库地址。

## 总结

Router 本身不做兑换数学，而是把“备币、调 Pair、校验”编织成一组接口，并叠加核心层省去的安全与便利。它绑定不可变的 `factory` 与 `WETH`：前者用于按需创建交易对，后者让只认 ERC20 的 Pair 能间接处理原生 ETH。添加流动性由 `_addLiquidity` 用 `quote` 算出最优配比、以最小值做滑点保护；移除流动性则返还 LP Token 取回代币，`WithPermit` 变体借 EIP-2612 把授权与移除压成一笔交易。兑换的核心是 `_swap`：沿路径逐跳调用各 Pair 的 `swap`，中间跳的输出直接发给下一跳 Pair，把多跳压缩进一次交易；`Router02` 进一步支持转账扣费代币，并修复了 `Router01` 中 `getAmountIn` 误调 `getAmountOut` 的 bug。至此，外围层的工具库与路由合约均已展开，核心层以极简换取可信，外围层以 Router 为入口补齐了用户所需的全部保护与便利。
