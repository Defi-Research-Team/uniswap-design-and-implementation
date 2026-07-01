# 外围层工具库

本章聚焦外围层三个无状态工具库：承担地址推导与量价估算的 `UniswapV2Library`、辅助读取预言机数据的 `UniswapV2OracleLibrary`，以及用于估算 LP 份额价值的 `UniswapV2LiquidityMathLibrary`。它们都不持有任何状态、只做纯计算（或仅以 `view` 方式读取链上数据），因此能被 Router、前端、聚合器乃至任意第三方协议无副作用地复用。

## UniswapV2Library

`UniswapV2Library` 是外围层最常被调用的库，Router 几乎所有操作都经它计算地址、查询储备量、估算兑换量。它由七个函数组成，下面按用途分组剖析。

### 排序与地址：sortTokens 与 pairFor

```solidity
// v2-periphery/contracts/libraries/UniswapV2Library.sol

function sortTokens(address tokenA, address tokenB) internal pure returns (address token0, address token1) {
    require(tokenA != tokenB, 'UniswapV2Library: IDENTICAL_ADDRESSES');
    (token0, token1) = tokenA < tokenB ? (tokenA, tokenB) : (tokenB, tokenA);
    require(token0 != address(0), 'UniswapV2Library: ZERO_ADDRESS');
}
```

`sortTokens` 把任意顺序的两个代币地址规范化为 `(token0, token1)`（较小者在前）。它正是第 7 章 Factory 的 `createPair` 里那行 `tokenA < tokenB ? ...` 的镜像，外围层必须与 Factory 采用**完全一致的排序规则**，原因有二：

- **确定性地址**：`pairFor` 计算 Pair 地址时，盐取 `keccak256(token0 ‖ token1)`，只有排序一致，算出的盐与地址才和 Factory 部署时相同。
- **储备量顺序**：Pair 内部把储备量存为 `(reserve0, reserve1)`（按 `token0`/`token1` 排序），`getReserves` 要把结果还原成调用者期望的 `(A, B)` 顺序，也依赖同一套排序。

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

`pairFor` 用 CREATE2 地址公式（第 7 章式 (1)）与恒定的 init code hash（常量 (2)）就地算出 Pair 地址，其原理已在第 7 章详述。这里只需记住它的价值：一个 `pure` 函数、零外部调用，让外围层无需先查询 Factory 就能反事实地定位任意 Pair。

### 储备量查询：getReserves

```solidity
function getReserves(address factory, address tokenA, address tokenB)
    internal view returns (uint reserveA, uint reserveB)
{
    (address token0,) = sortTokens(tokenA, tokenB);
    (uint reserve0, uint reserve1,) = IUniswapV2Pair(pairFor(factory, tokenA, tokenB)).getReserves();
    (reserveA, reserveB) = tokenA == token0 ? (reserve0, reserve1) : (reserve1, reserve0);
}
```

`getReserves` 把“算地址 → 读储备量 → 还原顺序”三步合一：先用 `pairFor` 定位 Pair，调用其 `getReserves()` 拿到按 `token0`/`token1` 排序的 `(reserve0, reserve1)`，再根据 `tokenA` 是否等于 `token0` 决定是否对调，从而**按调用者传入的 `(tokenA, tokenB)` 顺序**返回储备量。这样上层代码无需关心排序细节，传 `(A, B)` 就拿到 `(reserveA, reserveB)`。

### 等价数量：quote

```solidity
function quote(uint amountA, uint reserveA, uint reserveB) internal pure returns (uint amountB) {
    require(amountA > 0, 'UniswapV2Library: INSUFFICIENT_AMOUNT');
    require(reserveA > 0 && reserveB > 0, 'UniswapV2Library: INSUFFICIENT_LIQUIDITY');
    amountB = amountA.mul(reserveB) / reserveA;
}
```

`quote` 按当前储备量比例，计算与 `amountA` 个 tokenA _等价_ 的 tokenB 数量：

$$\text{amountB} = \text{amountA} \times \frac{\text{reserveB}}{\text{reserveA}} \tag{1}$$

它纯粹是储备量之比，**不扣手续费、不计价格影响**，因为它服务的是“按比例存入”而非“兑换”。下一章 Router 的 `_addLiquidity` 正是用它推算：给定想存入的 `amountADesired`，按池中价格应配多少 tokenB（`amountBOptimal`），据此判断用户提供的两种代币是否成比例。

### 兑换量估算：getAmountOut 与 getAmountIn

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

`getAmountOut` 的公式即第 7 章式 (5)，把 0.3% 手续费写成 $\frac{997}{1000}$：先从输入中预扣费用（`amountInWithFee = amountIn * 997`），再按恒定乘积算输出，全程用整数运算避免浮点。它是链下估算，Router 据此算出预期输出，再交给链上 `swap` 的 K 不变量检查兜底（第 7 章式 (3)）。

`getAmountIn` 是其逆运算：给定想要的输出量，反推需要多少输入。从带手续费的恒定乘积 $(x + 0.997\,\Delta x)(y - \Delta y) = x \cdot y$ 解出输入 $\Delta x$：

$$\Delta x = \frac{x \cdot \Delta y}{0.997\,(y - \Delta y)} \tag{2}$$

整数化（$0.997 = 997/1000$，分子分母同乘 1000）后即代码里的写法：

```solidity
function getAmountIn(uint amountOut, uint reserveIn, uint reserveOut) internal pure returns (uint amountIn) {
    require(amountOut > 0, 'UniswapV2Library: INSUFFICIENT_OUTPUT_AMOUNT');
    require(reserveIn > 0 && reserveOut > 0, 'UniswapV2Library: INSUFFICIENT_LIQUIDITY');
    uint numerator = reserveIn.mul(amountOut).mul(1000);
    uint denominator = reserveOut.sub(amountOut).mul(997);
    amountIn = (numerator / denominator).add(1);
}
```

注意末尾的 `.add(1)`。整数除法向下取整，而在“指定输出量”的模式下，链上 `swap` 的 K 检查要求实际收到的输入**不少于**理论值，若向下取整少收了一 wei，检查就会失败、交易回滚。因此这里主动加 1 向上取整，保证推算出的输入量一定够用。

### 多跳串联：getAmountsOut 与 getAmountsIn

很多代币对之间没有直接交易对，兑换需经中间代币完成，例如 A → B → C。`UniswapV2Library` 用一个代币地址数组 `path`（如 `[A, B, C]`）表达这条路径，相邻两项即一跳，每一跳对应一个独立的 Pair。

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

`getAmountsOut` 从头到尾**正向累加**：`amounts[0]` 是初始输入，每一跳用 `getAmountOut` 算出下一跳的输入，逐段推进，`amounts[末]` 即最终输出。`getAmountsIn` 则方向相反：

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

它从期望的最终输出 `amountOut` 出发**反向求解**：`amounts[末]` 是目标输出，倒着用 `getAmountIn` 逐跳推算前一跳所需的输出（也就是这一跳的输入），`amounts[0]` 即最初必须投入的总量。两者都把多跳问题分解成一连串单跳，每一跳独立查询自己的储备量、套用单跳公式，多跳只是把结果串起来。

## UniswapV2OracleLibrary

第 6 章指出，Pair 只负责把“价格 × 时长”累加进 `price0CumulativeLast`/`price1CumulativeLast`，TWAP 的计算交由外部读取者。`UniswapV2OracleLibrary` 正是为这些读取者提供的辅助，核心是 `currentCumulativePrices`。

### counterfactual 累计价格：currentCumulativePrices

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

要理解这段代码，先回顾 Pair 的累加时机：`price0CumulativeLast` 只在每个区块**首次**改变储备量时（即 `_update`）才更新一次。因此当你任意时刻读取它，读到的往往是“上一次 `_update` 时刻”的值，自那以后流逝的时间尚未被计入，累加器是“过时”的。

`currentCumulativePrices` 解决的就是这个滞后。它先读取链上的 `price0CumulativeLast`，若发现 `blockTimestampLast != blockTimestamp`（即距上次更新已过了一段时间），就**就地补算**那一段尚未累加的部分：用当前储备量算出价格（`FixedPoint.fraction(reserve1, reserve0)` 等价于第 6 章的 `UQ112x112.encode(reserve1).uqdiv(reserve0)`），乘以流逝的时间 `timeElapsed`，加到本地副本上。

这是一种 _反事实（counterfactual）_ 计算：它不调用 `sync` 去真正更新链上状态（那会改变储备量、消耗 Gas、还可能干扰其它逻辑），而是“假设现在更新了”，算出累加器**将会**变成的值。对只需读取 TWAP 的预言机来说，这个只读的“假设值”就够了。函数是 `view`，两次减法/加法的溢出与 Pair 内部一样是有意为之的无符号回绕（第 6 章）。`FixedPoint`、下文的 `Babylonian`/`FullMath` 都来自 Uniswap 的共享库 `@uniswap/lib`，是核心层之外的通用数值工具。

## UniswapV2LiquidityMathLibrary

前两个库服务于“兑换与读取”，`UniswapV2LiquidityMathLibrary` 则服务于“估值”：给定一份 LP 份额，它值多少 underlying 代币？难点在于池子的现货储备量可被单笔大额交易瞬时操纵，直接用现货储备量估值会被 _三明治攻击（sandwich attack）_ 利用。该库提供两条估值路径：一条直接读现货（廉价但可操纵），一条假设套利已把价格拉回“真实价”（抗操纵）。

### 套利到真实价：computeProfitMaximizingTrade 与 getReservesAfterArbitrage

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

`computeProfitMaximizingTrade` 接收一对“真实价格”`(truePriceTokenA : truePriceTokenB)`（即外部可信的 A、B 比价）与池子的现货储备量，求出把池子价格**恰好搬到真实价**的那笔 _利润最大化套利交易（profit-maximizing trade）_ 的方向与规模。

方向由第一行决定：比较池中隐含的 A 的价格（`reserveB/reserveA`，以 B 计）与真实价（`truePriceA/truePriceB`）。若池子里 A 偏贵，就把 A 卖进池子（`aToB = true`）；反之买 A。规模则令“这笔交易后的池价等于真实价”解出，代码用 `Babylonian.sqrt`（开方）与 `FullMath.mulDiv`（512 位全精度乘除）以整数精确实现。核心思想是：套利者会一直交易，直到池价与真实价无差可套，那时的储备量就是“去操纵后”的公允储备量。

`getReservesAfterArbitrage` 读取现货储备量，调用上式算出套利交易，再用 `UniswapV2Library.getAmountOut` 把这笔交易的效果施加到储备量上，返回套利后的 `(reserveA, reserveB)`。

### LP 份额估值：getLiquidityValue 与 getLiquidityValueAfterArbitrageToPrice

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

`computeLiquidityValue` 是估值的内核。LP 份额按比例对应池中的资产：

$$\text{tokenAAmount} = \text{reserveA} \times \frac{\text{liquidityAmount}}{\text{totalSupply}}$$

有一个细节：若协议费开启（第 5 章），Pair 自上次结算以来累积的协议费尚未铸造成 LP Token，`totalSupply` 因此被低估。此处用第 5 章式 (13) 的协议费铸币公式（分母里的 `5` 即 $1/6$ 副费率的痕迹）算出待铸的 `feeLiquidity`，加到 `totalSupply` 上作为修正，使估值不被这部分“隐含稀释”扭曲。

`getLiquidityValue` 直接读现货储备量与参数，调用 `computeLiquidityValue`。源码注释明确警告：**它可被三明治攻击操纵**，攻击者可瞬时推高现货储备量再撤回，使估值短暂虚高。因此更稳妥的是 `getLiquidityValueAfterArbitrageToPrice`：它接收一个可信的真实价，先经 `getReservesAfterArbitrage` 算出“套利后”的公允储备量，再估值。由于任何对现货储备量的操纵都会被套利者迅速抹平、拉回真实价，攻击者无法从虚高的现货中获利，估值也就抗操纵了。代价是必须额外提供一个可信的外部价格。

## 总结

`UniswapV2Library` 是外围层的主干：`sortTokens` 与 Factory 排序规则一致，奠定确定性地址与储备量顺序的基础；`pairFor` 让外围层零外部调用地反事实算出 Pair 地址；`getReserves` 把算地址、读储备量、还原顺序三步合一；`quote` 按储备量比例给出等价数量；`getAmountOut`/`getAmountIn` 是带 0.3% 手续费的正反向兑换估算，`getAmountsOut`/`getAmountsIn` 把多跳兑换拆成一串单跳分别累加。`UniswapV2OracleLibrary` 用反事实计算补算 Pair 累加器尚未计入的“价格 × 时长”，是构建 TWAP 预言机的读取辅助。`UniswapV2LiquidityMathLibrary` 服务于 LP 份额估值：先求出把池价搬到真实价的套利交易、得到去操纵后的公允储备量，再按比例估值并修正待铸协议费；直接读现货的 `getLiquidityValue` 易遭三明治操纵，而 `getLiquidityValueAfterArbitrageToPrice` 因假设套利已发生而抗操纵，代价是需提供可信外部价格。
