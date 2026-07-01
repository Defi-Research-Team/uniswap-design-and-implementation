# 资金池

第 3 章把核心层概括为两个合约：Factory 创建并注册交易对，每个 Pair 既是一个管理两种代币储备量的 AMM 资金池，又是一份发行 LP Token 的 ERC20。本章走进这两个合约的实现：前半分析 Factory 如何用 `create2` 把新 Pair 部署到完全可预测的地址、并以极小的治理面掌管协议费的开关；后半逐层剖析 Pair 的全部机制，包括状态记录、流动性的添加与移除、交易执行（含闪电兑换），以及 `sync` 与 `skim` 处理余额与储备量不同步的边角情形。手续费、协议费、预言机等原理已在第 5、6 章展开，本章直接引用其结论，聚焦合约实现。

## 工厂合约

Factory 是整个 V2 系统的“注册中心”，负责创建交易对并登记其地址。本节走进 `UniswapV2Factory` 的实现，看它如何用一行 `create2` 把一个新 Pair 部署到完全可预测的地址上、为什么这一设计让 Pair 地址能在创建前就被算出，以及它如何以极小的治理面掌管协议费的开关。

### 状态

Factory 的状态非常精简，只有两类：交易对登记表，与协议费治理。

```solidity
// v2-core/contracts/UniswapV2Factory.sol

address public feeTo;           // 协议费接收地址；为 address(0) 表示关闭
address public feeToSetter;     // 有权改动 feeTo 的账户，构造函数中唯一被设置的参数

mapping(address => mapping(address => address)) public getPair;  // 交易对登记表，双向
address[] public allPairs;                                        // 所有已创建 Pair 的有序列表

event PairCreated(address indexed token0, address indexed token1, address pair, uint);
```

`getPair` 是一张双向映射：给定任意顺序的两个代币地址，都能直接查到对应 Pair。`allPairs` 则保存所有 Pair 的创建顺序，其长度即系统中交易对的总数（通过 `allPairsLength` 暴露）。`feeTo` 与 `feeToSetter` 用于协议费治理，详见本节末尾。

注意 Factory **没有** `owner`、也**没有任何升级机制**。除了协议费相关的两个函数，它创建交易对的逻辑一经部署便不可更改，这是核心层“极简、不可变”哲学的体现（见第 3 章）。

### 创建资金池

`createPair` 是 Factory 的核心，负责把一对代币变成一个部署好的 Pair：

```solidity
function createPair(address tokenA, address tokenB) external returns (address pair) {
    require(tokenA != tokenB, 'UniswapV2: IDENTICAL_ADDRESSES');
    (address token0, address token1) = tokenA < tokenB ? (tokenA, tokenB) : (tokenB, tokenA);
    require(token0 != address(0), 'UniswapV2: ZERO_ADDRESS');
    require(getPair[token0][token1] == address(0), 'UniswapV2: PAIR_EXISTS');

    bytes memory bytecode = type(UniswapV2Pair).creationCode;
    bytes32 salt = keccak256(abi.encodePacked(token0, token1));
    assembly {
        pair := create2(0, add(bytecode, 32), mload(bytecode), salt)
    }
    IUniswapV2Pair(pair).initialize(token0, token1);

    getPair[token0][token1] = pair;
    getPair[token1][token0] = pair;
    allPairs.push(pair);
    emit PairCreated(token0, token1, pair, allPairs.length);
}
```

它的流程可以拆成四步：

**一、规范化与校验。** 两个代币地址必须不同，且都不能是零地址。更关键的是把它们**排序**：`token0` 取较小者、`token1` 取较大者。这样无论调用者以何种顺序传入 `(A, B)` 或 `(B, A)`，规范化后都得到同一组 `(token0, token1)`，从而保证一个代币对全局只有一个 Pair。校验“是否已存在”也因此在排序之后进行，且只需检查一个方向（`getPair[token0][token1]`）即可，注释里的“single check is sufficient”正是此意。

**二、CREATE2 部署。** 取 Pair 的创建字节码 `type(UniswapV2Pair).creationCode`，用 `salt = keccak256(token0 ‖ token1)` 作盐，通过内联汇编 `create2` 部署。`create2(0, add(bytecode, 32), mload(bytecode), salt)` 的四个参数依次是：转账金额（0）、字节码在内存中的起始位置（跳过 `bytes` 变量的 32 字节长度前缀）、字节码长度（从该前缀读出）、盐。`create2` 是 EVM 的确定性部署操作码，部署地址完全由部署者、盐、字节码三者决定。

**三、初始化。** 部署完成后立即调用 `IUniswapV2Pair(pair).initialize(token0, token1)`，把两个代币地址绑定到新 Pair（本章资金池一节将分析 `initialize` 只允许 Factory 调用）。

**四、登记与事件。** 把新地址同时写入映射的两个方向（使任意顺序的查询都能命中），压入 `allPairs`，最后 emit `PairCreated`，事件的最后一个参数是 `allPairs.length`，即该 Pair 的序号。

### 确定性地址

`create2` 最有价值的特性是：**部署地址在部署之前就能算出来**。CREATE2 的地址公式是：

$$\text{address} = \text{keccak256}(\texttt{0xff} \,\|\, \text{deployer} \,\|\, \text{salt} \,\|\, \text{keccak256}(\text{init code}))[-20\text{:}] \tag{1}$$

其中 `deployer` 是 Factory，`salt` 是 `keccak256(token0 ‖ token1)`，二者都是已知量。剩下的关键在于 `keccak256(init code)`，它必须也是个常量，整个地址才可预测。

这正是 `initialize` 与构造函数分离的根本原因。`init code` 由合约的创建字节码加上**构造函数参数**拼接而成。若构造函数接收 token 地址作参数，参数就会被拼进 `init code`，使 `keccak256(init code)` 随参数变化、地址也随之变化，虽仍可计算，却要为每个代币对单独求哈希。Uniswap 刻意让 Pair 的构造函数**无参**（只记 `factory = msg.sender`），token 地址改由独立的 `initialize` 设置；如此一来 `creationCode` 是一份固定常量，其哈希也是固定常量：

$$\text{INIT\_CODE\_HASH} = \text{keccak256}(\text{creationCode})$$

$$= \texttt{0x96e8ac4277198ff8b6f785478aa9a39f403cb768dd02cbee326c3e7da348845f} \tag{2}$$

有了这个常量，任何人都能在不查询链上状态的情况下算出某个 Pair 的地址。外围层的 `UniswapV2Library.pairFor` 正是这么做的：

```solidity
// v2-periphery/contracts/libraries/UniswapV2Library.sol

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

注意它是 `pure` 函数，全程不发起任何外部调用，纯靠公式 (1) 与常量 (2) 就地算出地址。这意味着 Router、前端、聚合器都可以在 Pair **尚未创建**时反事实地推算出它将来的地址，直接向该地址查询储备量或预构造交易，而无需先调用 Factory。这是 V2 用户体验与可组合性的一项基石。`pairFor` 的完整分析见下一章外围层工具库。

> [!note]
> 常量 (2) 是官方主网部署的 `UniswapV2Pair` 的 init code hash。它取决于合约的具体编译结果（版本、优化设置、源码）；若 Factory 部署的是不同编译产物，该哈希会不同，`pairFor` 也必须换用对应值。这也是为什么自建 fork 必须重新计算并替换此常量。

### 协议费治理

Factory 掌管协议费的开关，且只有两个函数、一道权限：

```solidity
function setFeeTo(address _feeTo) external {
    require(msg.sender == feeToSetter, 'UniswapV2: FORBIDDEN');
    feeTo = _feeTo;
}

function setFeeToSetter(address _feeToSetter) external {
    require(msg.sender == feeToSetter, 'UniswapV2: FORBIDDEN');
    feeToSetter = _feeToSetter;
}
```

`setFeeTo` 设定协议费的接收地址，`setFeeToSetter` 转移治理权本身。两者都仅允许当前的 `feeToSetter` 调用。

回顾第 5 章，Pair 的 `_mintFee` 以 `feeTo != address(0)` 判断协议费是否开启。而 Factory 构造函数**只设置 `feeToSetter`、从不设置 `feeTo`**，故 `feeTo` 初值为 `address(0)`，协议费默认关闭。要开启，`feeToSetter` 须显式调用 `setFeeTo` 指定一个接收地址。这一设计把“是否向协议方抽成”完整地交给治理决定，部署之初对用户保持完全免费。

### 不可变性

Factory 没有所有者、没有代理、没有暂停开关、没有升级路径。`feeToSetter` 是唯一的特权角色，而它的权力也仅限于改动 `feeTo` 与转让自己，它**无法**修改交易公式、手续费率、Pair 创建逻辑或已部署 Pair 的任何行为。

这种近乎绝对的不可变性是核心层换取“可信”与“可复用”的代价（见第 3 章）。正因为任何协议或用户都能确信 V2 的核心规则永不变更，他们才敢把资金长期托付给这些合约、或在它之上构建外围层与第三方应用。可演进的部分（Router、工具库、新版本）全部留在外围层与未来的新合约里，核心则一经部署便凝固。

## 资金池合约

### 状态

Pair 合约的全部运行状态集中在一组变量里。先认识它们，后续各节的逻辑都围绕这些状态展开：

```solidity
// v2-core/contracts/UniswapV2Pair.sol

address public factory;             // 部署该 Pair 的 Factory，在构造函数中固定为 msg.sender
address public token0;              // 交易对的两种代币，由 initialize 一次性设置
address public token1;

uint112 private reserve0;           // 与 reserve1、blockTimestampLast 共同打包进单个存储槽
uint112 private reserve1;           // uses single storage slot, accessible via getReserves
uint32  private blockTimestampLast; // uses single storage slot, accessible via getReserves

uint public price0CumulativeLast;   // 预言机价格累加器，第 6 章展开
uint public price1CumulativeLast;
uint public kLast;                  // reserve0 * reserve1，最近一次流动性事件后的值，本章下文展开

uint private unlocked = 1;
modifier lock() {
    require(unlocked == 1, 'UniswapV2: LOCKED');
    unlocked = 0;
    _;
    unlocked = 1;
}
```

前三个地址变量定义了这个 Pair 的身份。`factory` 指向部署它的工厂合约，在构造函数中固定为 `msg.sender`，之后不再改变；Pair 通过它反向查询协议费的开关状态（`feeTo`）。`token0` 与 `token1` 是该交易对所管理的两种代币，由 Factory 调用 `initialize` 一次性写入。两者按地址数值大小排序：`token0` 取较小地址、`token1` 取较大地址，与 Factory 创建交易对时的规范化一致，从而保证任意一对代币全局只有一个 Pair，且无论查询顺序如何都得到一致的 `token0`/`token1`。

其中最核心的是 `reserve0` 与 `reserve1`，即两种代币的 _储备量（reserve）_。值得注意的是 `reserve0`、`reserve1` 与 `blockTimestampLast` 三个变量被打包进同一个 256 位存储槽（各自占 112、112、32 位），这是为了节省 Gas：它们总是一起读取、一起更新，放在一个槽里只需一次存储访问。对外通过 `getReserves` 一次性返回三者：

```solidity
function getReserves() public view returns (uint112 _reserve0, uint112 _reserve1, uint32 _blockTimestampLast) {
    _reserve0 = reserve0;
    _reserve1 = reserve1;
    _blockTimestampLast = blockTimestampLast;
}
```

`price0CumulativeLast` 与 `price1CumulativeLast` 是为预言机持续累加的价格数据，其原理详见第 6 章。`kLast` 记录最近一次流动性事件后两种代币储备量的乘积（即 $k$），它是协议费结算的记账基准：每次添加或移除流动性时，合约比较当前 $k$ 与 `kLast` 的增长，按第 5 章推导的公式为协议地址铸造 LP Token。其完整工作机制（含懒惰评估与关闭清零）将在下文“协议费”小节结合 `_mintFee` 的实现展开。

`unlocked` 配合 `lock` 修饰器构成一把 _重入锁（reentrancy lock）_：进入函数前置 0、退出后置 1，使核心函数无法在执行中途被重入。由于这些函数都遵循先转账、后结算的模式，重入保护不可或缺。重入攻击的原理与 `lock` 修饰器的实现细节，放在下文独立的“重入锁”小节展开。

### 初始化

最后是 Pair 的诞生方式。构造函数极其简单，只记下是谁部署了自己：

```solidity
constructor() public {
    factory = msg.sender;
}
```

而交易对的两种代币则由独立的 `initialize` 设置，且只允许 Factory 调用一次：

```solidity
function initialize(address _token0, address _token1) external {
    require(msg.sender == factory, 'UniswapV2: FORBIDDEN');
    token0 = _token0;
    token1 = _token1;
}
```

为什么不在构造函数里直接传入代币地址？因为 Factory 用 `CREATE2` 部署 Pair，需要一个不带参数的构造函数，才能让 Pair 的创建字节码保持恒定、从而可以反事实地推算地址。这一设计的完整含义已在本章 Factory 一节展开。这里只需知道：每个 Pair 在创建后由 Factory 调用 `initialize` 绑定一对代币，之后 `token0`/`token1` 便不再改变。

### 重入锁

Pair 的核心函数都依赖重入锁来保证安全。在分析具体的流动性与交易逻辑之前，先理解这一机制。

#### 重入攻击的原理

_重入攻击（reentrancy attack）_是智能合约最经典的漏洞之一。当合约在外部调用尚未返回、内部状态尚未更新时，攻击者利用这一时间窗口重新进入合约，在不一致的状态下触发非预期行为。2016 年的 The DAO 事件因此损失超过 1.5 亿美元，最终导致以太坊硬分叉。

以下是一个简化的脆弱合约，改编自以太坊编程指南：

```solidity
contract EtherStore {
    mapping(address => uint256) balances;

    function depositFunds() public payable {
        balances[msg.sender] += msg.value;
    }

    function withdrawFunds() public {
        uint256 _amt = balances[msg.sender];
        (bool res, ) = msg.sender.call{value: _amt}("");  // 先转账
        require(res);
        balances[msg.sender] -= _amt;                      // 后扣减余额
    }
}
```

漏洞在于 `withdrawFunds`：合约先通过 `call` 把 ether 转给调用者，之后再扣减余额。若调用者是恶意合约，其 `receive` 函数会在收到 ether 的瞬间被触发，此时余额尚未扣减，攻击者便可再次调用 `withdrawFunds`，如此循环直到合约被掏空：

```solidity
contract Attack {
    EtherStore etherStore;
    constructor(address _addr) { etherStore = EtherStore(_addr); }

    function attack() public payable {
        etherStore.depositFunds{value: 1 ether}();
        etherStore.withdrawFunds();
    }

    receive() external payable {
        if (address(etherStore).balance >= 1 ether)
            etherStore.withdrawFunds();  // 重入：余额尚未扣减
    }
}
```

根因是外部调用与状态更新的顺序：合约在尚未完成结算时就交出了控制权。

#### Pair 的重入锁

Pair 面临同样的风险。它的核心函数 `mint`、`burn`、`swap` 都遵循先转移代币、再根据余额差结算的模式。尤其是 `swap`，还会回调外部地址的 `uniswapV2Call`（闪电兑换）。若攻击者在回调中重新进入 `mint` 或 `swap`，便能在储备量尚未更新的窗口内牟利。

V2 的解法是一个极简的互斥锁：

```solidity
uint private unlocked = 1;
modifier lock() {
    require(unlocked == 1, 'UniswapV2: LOCKED');
    unlocked = 0;
    _;
    unlocked = 1;
}
```

`unlocked` 初值为 1。进入被 `lock` 修饰的函数时检查其是否为 1，随即置 0 上锁；函数体执行完毕后恢复为 1 解锁。若攻击者在执行中途尝试重入，`require(unlocked == 1)` 会因 `unlocked` 仍为 0 而回滚，攻击无法成立。

Pair 中所有会改变状态的核心函数都带 `lock` 修饰器：`mint`、`burn`、`swap`、`sync`、`skim`。它们共享同一把锁（同一个 `unlocked` 变量），因此彼此互斥：任一核心函数执行期间，其余核心函数都无法重入，从而确保 Pair 在每个时刻至多有一个核心操作在改变状态。

### 流动性管理

流动性是 AMM 的根基。Pair 通过 `mint` 和 `burn` 两个函数管理流动性的增减：`mint` 让 LP 注入代币并换取 LP Token，`burn` 则是逆操作，LP 交还 LP Token 按比例取回代币。两个函数都建立在 `_update` 这一基础函数之上，它负责把合约的真实余额写入储备量，是所有改变储备量操作的统一出口。此外，每次 `mint` 或 `burn` 在计算 LP Token 之前都会先调用 `_mintFee` 结算协议费。本节自下而上展开：先看 `_update` 如何同步储备量，再分别剖析 `mint`（添加流动性）与 `burn`（移除流动性）的完整逻辑，最后以 `_mintFee` 收尾，说明协议费如何在流动性事件中落地。

#### 更新储备量

在分析 `mint` 和 `burn` 之前，需要先理解一个基础函数。Pair 合约中所有改变储备量的操作最终都通过 `_update` 完成：

```solidity
// v2-core/contracts/UniswapV2Pair.sol

function _update(uint balance0, uint balance1, uint112 _reserve0, uint112 _reserve1) private {
    require(balance0 <= uint112(-1) && balance1 <= uint112(-1), 'UniswapV2: OVERFLOW');
    uint32 blockTimestamp = uint32(block.timestamp % 2**32);
    uint32 timeElapsed = blockTimestamp - blockTimestampLast;
    if (timeElapsed > 0 && _reserve0 != 0 && _reserve1 != 0) {
        price0CumulativeLast += uint(UQ112x112.encode(_reserve1).uqdiv(_reserve0)) * timeElapsed;
        price1CumulativeLast += uint(UQ112x112.encode(_reserve0).uqdiv(_reserve1)) * timeElapsed;
    }
    reserve0 = uint112(balance0);
    reserve1 = uint112(balance1);
    blockTimestampLast = blockTimestamp;
    emit Sync(reserve0, reserve1);
}
```

`_update` 做两件事：

1. **更新预言机累加价格**：在每个区块的第一次储备量更新时，将当前价格乘以时间间隔累加到 `price0CumulativeLast` 和 `price1CumulativeLast`。这是预言机的核心数据源，第 6 章详细分析
2. **同步储备量**：将合约的实际代币余额写入 `reserve0` 和 `reserve1`

> [!important]
> `_update` 的前两个参数是 `balance0` 和 `balance1`（合约的实际代币余额），而非任何计算出来的值。这是 V2 贯穿始终的设计原则：**储备量总是反映合约的真实余额**。`mint`、`burn`、`swap` 无一例外，都是先把代币转入/转出合约、再用真实余额覆盖储备量。

还要注意溢出检查 `require(balance0 <= uint112(-1))`。虽然 `uint112` 的最大值约 $5.19 \times 10^{33}$，对于绝大多数代币来说足够大（18 位精度的代币最大约 $10^{18}$），但这个检查确保了储备量能安全地写回打包存储槽。

#### 添加流动性

`mint` 根据池中是否已有流动性分两种情况。首次添加（`totalSupply == 0`）时没有历史储备量可供参照，流动性按注入量的几何平均数 $\sqrt{\Delta x \cdot \Delta y}$ 计算，并永久锁定 1000 个最小流动性以防池被掏空后价格归零。后续添加时，已有储备量比例作为基准，新增 LP Token 取两种代币各自算出的候选值中较小者，确保不会凭空多铸。两种情况共享同一套调用约定与余额差推断逻辑。

##### 调用约定

`mint` 函数是流动性提供者向池中注入资金的入口。第 1 章推导了流动性管理的数学原理，现在来看它如何落地为合约代码。
Pair 合约的 `mint` 遵循一个特殊的调用约定：**调用者先将要存入的代币转入 Pair 合约，然后再调用 `mint`**。

```solidity
function mint(address to) external lock returns (uint liquidity) {
    (uint112 _reserve0, uint112 _reserve1,) = getReserves();
    uint balance0 = IERC20(token0).balanceOf(address(this));
    uint balance1 = IERC20(token1).balanceOf(address(this));
    uint amount0 = balance0.sub(_reserve0);
    uint amount1 = balance1.sub(_reserve1);
    // ...
}
```

合约通过比较当前余额与上次记录的储备量来计算新增的代币数量：

$$\text{amount0} = \text{balance0} - \text{reserve0}$$
$$\text{amount1} = \text{balance1} - \text{reserve1}$$

这就是为什么 `mint` 不需要接收代币数量参数，合约自己从余额差中推断。这种模式被称为 _乐观转账（optimistic transfer）_：先假设调用者已经转入了代币，通过余额差来验证。它把“转入”这一外部动作排除在核心合约之外，使 Pair 不必信任任何人提供的金额。

##### 首次添加

当池子第一次添加流动性时（`totalSupply == 0`），流动性按几何平均数计算：

```solidity
if (_totalSupply == 0) {
    liquidity = Math.sqrt(amount0.mul(amount1)).sub(MINIMUM_LIQUIDITY);
    _mint(address(0), MINIMUM_LIQUIDITY);
}
```

回顾第 1 章的公式，流动性 $L = \sqrt{xy}$。这里 `Math.sqrt(amount0 * amount1)` 正是 $\sqrt{\Delta x \cdot \Delta y}$。

首次添加时还有一个特殊处理：**永久锁定最小流动性**。`MINIMUM_LIQUIDITY = 10^3 = 1000` 个 LP Token 被铸造给地址 `0`（即销毁），从总供应量中永久移除。

为什么需要锁定最小流动性？考虑一个极端场景：如果池子的流动性被完全移除（`totalSupply` 降为 0），那么下一个添加流动性的人可以凭空设定池子的初始价格，因为此时没有任何历史储备量比例可供参照。锁定 1000 个 LP Token 确保 `totalSupply` 永远不会降为 0，从而保证池子始终保留一份有效的储备量比例作为价格参考。

1000 个 LP Token 的实际价值取决于首次注入的资金量。如果首次注入了价值 \$10,000 的代币，则 1000 LP Token 大约值 $\frac{1000}{\sqrt{10^6}} \times \$10{,}000 \approx \$10$。对于大多数池子来说，这是一笔可以忽略不计的代价。

##### 后续添加

当池子已有流动性时，新增 LP Token 按两种代币中**比例较小**的一个计算：

```solidity
} else {
    liquidity = Math.min(
        amount0.mul(_totalSupply) / _reserve0,
        amount1.mul(_totalSupply) / _reserve1
    );
}
```

回顾第 1 章的流动性增量公式：$\Delta L = L \cdot \frac{\Delta x}{x}$。展开得：

$$\Delta L = \Delta x \cdot \frac{L}{x} = \Delta x \cdot \frac{\text{totalSupply}}{\text{reserve}}$$

这里计算了两个候选值：

- $\Delta x \cdot \frac{\text{totalSupply}}{\text{reserve0}}$
- $\Delta y \cdot \frac{\text{totalSupply}}{\text{reserve1}}$

在理想情况下（提供的两种代币完全按当前价格比例），这两个值应该相等。但实际上，由于代币精度、舍入等原因，提供的比例可能与池中价格有微小偏差。取 `min` 确保不会凭空创造出多于应得的 LP Token，多出的那部分代币相当于无偿留在了池子里，对所有既有 LP 有利。

##### 完整流程

将以上部分串起来，`mint` 的完整流程是：

```solidity
function mint(address to) external lock returns (uint liquidity) {
    (uint112 _reserve0, uint112 _reserve1,) = getReserves();
    uint balance0 = IERC20(token0).balanceOf(address(this));
    uint balance1 = IERC20(token1).balanceOf(address(this));
    uint amount0 = balance0.sub(_reserve0);
    uint amount1 = balance1.sub(_reserve1);

    bool feeOn = _mintFee(_reserve0, _reserve1);
    uint _totalSupply = totalSupply;
    if (_totalSupply == 0) {
        liquidity = Math.sqrt(amount0.mul(amount1)).sub(MINIMUM_LIQUIDITY);
        _mint(address(0), MINIMUM_LIQUIDITY);
    } else {
        liquidity = Math.min(amount0.mul(_totalSupply) / _reserve0, amount1.mul(_totalSupply) / _reserve1);
    }
    require(liquidity > 0, 'UniswapV2: INSUFFICIENT_LIQUIDITY_MINTED');
    _mint(to, liquidity);

    _update(balance0, balance1, _reserve0, _reserve1);
    if (feeOn) kLast = uint(reserve0).mul(reserve1);
    emit Mint(msg.sender, amount0, amount1);
}
```

流程中的关键顺序是：

1. 读取旧储备量，查询当前余额，计算新增代币数量
2. 调用 `_mintFee` 结算协议费（如果开启）；详见下文“协议费”小节
3. 根据 `totalSupply` 是否为零，计算应铸造的 LP Token 数量
4. 铸造 LP Token 给接收者
5. 更新储备量
6. 如果协议费开启，记录当前的 $k$ 值供下次费用计算使用

#### 移除流动性：burn

`burn` 是 `mint` 的逆操作，LP 返还 LP Token 并按比例取回两种代币。

```solidity
function burn(address to) external lock returns (uint amount0, uint amount1) {
    (uint112 _reserve0, uint112 _reserve1,) = getReserves();
    address _token0 = token0;
    address _token1 = token1;
    uint balance0 = IERC20(_token0).balanceOf(address(this));
    uint balance1 = IERC20(_token1).balanceOf(address(this));
    uint liquidity = balanceOf[address(this)];

    bool feeOn = _mintFee(_reserve0, _reserve1);
    uint _totalSupply = totalSupply;
    amount0 = liquidity.mul(balance0) / _totalSupply;
    amount1 = liquidity.mul(balance1) / _totalSupply;
    require(amount0 > 0 && amount1 > 0, 'UniswapV2: INSUFFICIENT_LIQUIDITY_BURNED');
    _burn(address(this), liquidity);
    _safeTransfer(_token0, to, amount0);
    _safeTransfer(_token1, to, amount1);
    balance0 = IERC20(_token0).balanceOf(address(this));
    balance1 = IERC20(_token1).balanceOf(address(this));

    _update(balance0, balance1, _reserve0, _reserve1);
    if (feeOn) kLast = uint(reserve0).mul(reserve1);
    emit Burn(msg.sender, amount0, amount1, to);
}
```

##### 调用约定

与 `mint` 类似，`burn` 也遵循先转账后操作的约定：调用者先将 LP Token 转入 Pair 合约，然后调用 `burn`。合约通过 `balanceOf[address(this)]` 获取转入的 LP Token 数量。

##### 按比例提取

LP Token 代表池中的份额比例。移除流动性时，每种代币的提取量按份额计算：

$$\text{amount0} = \text{liquidity} \times \frac{\text{balance0}}{\text{totalSupply}}$$
$$\text{amount1} = \text{liquidity} \times \frac{\text{balance1}}{\text{totalSupply}}$$

注意这里用的是 `balance`（实际余额）而非 `reserve`（记录的储备量）。由于手续费以增加余额的方式留在池中，`balance` 可能略大于 `reserve`。使用 `balance` 确保了 LP 可以获得手续费累积带来的收益，这正是 LP 获得交易手续费的机制：手续费留在池中，增大了余额，使得每个 LP 按比例提取时能分到更多。

##### 完整流程

1. 读取储备量，查询代币余额，获取转入的 LP Token 数量
2. 调用 `_mintFee` 结算协议费
3. 按 LP Token 占总供应量的比例计算可提取的两种代币数量
4. 销毁 LP Token
5. 转出代币给接收者
6. 重新查询余额（转账后余额可能因转账费用而变化）
7. 更新储备量

#### 协议费

每次 `mint` 或 `burn` 在计算 LP Token 之前，都会先调用 `_mintFee` 结算自上次流动性事件以来累积的协议费。`_mintFee` 是第 5 章协议费公式的合约实现：

```solidity
function _mintFee(uint112 _reserve0, uint112 _reserve1) private returns (bool feeOn) {
    address feeTo = IUniswapV2Factory(factory).feeTo();
    feeOn = feeTo != address(0);
    uint _kLast = kLast; // gas savings
    if (feeOn) {
        uint rootK = Math.sqrt(uint(_reserve0).mul(_reserve1));
        uint rootKLast = Math.sqrt(_kLast);
        if (rootK > rootKLast) {
            uint numerator = totalSupply.mul(rootK.sub(rootKLast));
            uint denominator = rootK.mul(5).add(rootKLast);
            uint liquidity = numerator / denominator;
            if (liquidity > 0) _mint(feeTo, liquidity);
        }
    } else if (_kLast != 0) {
        kLast = 0;
    }
}
```

它的逻辑可以对照第 5 章逐行理解。

首先，通过 `IUniswapV2Factory(factory).feeTo()` 读取协议费接收地址。`feeOn = feeTo != address(0)` 判断协议费是否开启：只有当治理通过 Factory 设定了非零的 `feeTo` 时才生效（协议费默认关闭，详见本章工厂合约一节与第 5 章）。

当 `feeOn` 为真时，结算累积的协议费。`rootK` 是当前 $\sqrt{k}$，`rootKLast` 是上次结算时记录的 $\sqrt{k}$（即 $\sqrt{\text{kLast}}$）。若 `rootK > rootKLast`，说明自上次结算以来交易手续费的累积使 $k$ 增长了，增长量 $\sqrt{k_2} - \sqrt{k_1}$ 即可分配的手续费（第 5 章式 (10)）。据此为 `feeTo` 地址铸造 LP Token，铸币量正是第 5 章式 (13)：

$$\text{liquidity} = \frac{\text{totalSupply} \times (\text{rootK} - \text{rootKLast})}{5 \times \text{rootK} + \text{rootKLast}}$$

分子是 $\text{totalSupply} \times (\sqrt{k_2} - \sqrt{k_1})$，分母是 $5\sqrt{k_2} + \sqrt{k_1}$，与式 (13) 逐项对应，其中系数 5 来自协议费率 $\phi = 1/6$（即 $1/\phi - 1 = 5$）。协议方通过这笔新铸的 LP Token 分享池中累积的手续费，靠稀释既有 LP 的份额来兑现。

`else if (_kLast != 0)` 分支处理协议费关闭的情况。一旦 `feeOn` 为假而 `kLast` 不为零，说明协议费刚被关闭（`feeTo` 被设回零地址）。此时把 `kLast` 清零，擦除关闭前的记账基准。这确保协议费即便日后重新开启，也不会回头补收关闭期间的费用；关闭即意味着那段窗口的手续费全部让渡给了 LP。

`_mintFee` 返回 `feeOn`，调用方据此决定是否在结算后刷新 `kLast`。回到 `mint` 和 `burn` 的末尾：

```solidity
if (feeOn) kLast = uint(reserve0).mul(reserve1);
```

当协议费开启时，把当前 $k$ 写入 `kLast`，作为下次结算的新基准。这种不在每笔交易时收取、而只在添加或移除流动性时一次性结算的设计，称为懒惰评估。

它依赖一个关键事实：每次结算末尾，记账基准被刷新为当前 $k$（合约中即更新 `kLast`），而流动性事件虽然也改变 $k$，但会立即把基准更新到新值、相当于把自己的影响清零。因此在两次流动性事件之间，唯一能改变 $k$ 的只有交易，下次结算看到的增长 $\sqrt{k_2} - \sqrt{k_1}$ 恰好等于这段窗口内累积的纯手续费，不多不少。

懒惰评估带来三方面好处：每笔交易无需额外的费用计算与铸造，核心交易路径保持极简；作为基准的乘积只在结算时更新，而非每笔交易都写入存储；多笔交易的手续费累积后一次性计算，摊薄了整数除法的精度损失。代价是若长时间无人添加或移除流动性，累积的协议费可能相当可观，但由于费用以 LP Token 形式发放，且铸造量由第 5 章式 (13) 严格限定、不会超过应得份额，因此不存在多收的安全问题，最坏只是协议方"忘记"收取。

### 交易

`swap` 是 Pair 中执行交易的核心函数，也是 V2 最精巧的部分。和 `mint`/`burn` 一样，它遵循乐观转账的思路，但方向相反：**先把输出代币转给调用者，再核对是否收到了足够的输入代币**。

#### 乐观转账

到目前为止，`swap` 描述的是普通交易：输入代币在 `swap` 之前就已转入。但代码里有一行关键的回调：

```solidity
if (data.length > 0) IUniswapV2Callee(to).uniswapV2Call(msg.sender, amount0Out, amount1Out, data);
```

当调用者传入非空的 `data` 时，Pair 在**转出输出代币之后、K 不变量检查之前**，回调 `to` 地址上的 `uniswapV2Call`。这个时序是 V2 实现闪电兑换的根基：

![闪电兑换时序](images/ch04/flash_swap.png)

_图 1　闪电兑换的执行时序。Pair 先乐观地把输出代币转给调用者，随后回调 `uniswapV2Call`；调用者在回调中可任意使用这些代币（套利、转账、还款），回调返回后 Pair 才执行 K 不变量检查，确保调用者已归还足够的输入代币。_

由于回调发生在 K 检查之前，调用者在 `uniswapV2Call` 中已经“拿到”了输出代币，可以拿去做任何事，比如套利、搬运到别的池子，甚至当作闪电贷使用，只要回调结束前把等价（含 0.3% 手续费）的输入代币还回 Pair，使随后的 K 检查通过即可。这带来两项能力：

- **无需抵押的借贷**：可以先借出一种代币、在回调中完成操作后再归还，全程在一笔交易内完成，无需任何押品
- **多跳套利**：可以用 A 换出 B、在回调里再把 B 换成 C、最终归还足够的 A，把一条套利路径压缩进一次 `swap`

如果回调结束后 K 检查未通过，整笔交易回滚，Pair 状态原样不变，因此闪电兑换对资金池是安全的。

```solidity
function swap(uint amount0Out, uint amount1Out, address to, bytes calldata data) external lock {
    require(amount0Out > 0 || amount1Out > 0, 'UniswapV2: INSUFFICIENT_OUTPUT_AMOUNT');
    (uint112 _reserve0, uint112 _reserve1,) = getReserves();
    require(amount0Out < _reserve0 && amount1Out < _reserve1, 'UniswapV2: INSUFFICIENT_LIQUIDITY');

    uint balance0;
    uint balance1;
    {
        address _token0 = token0;
        address _token1 = token1;
        require(to != _token0 && to != _token1, 'UniswapV2: INVALID_TO');
        if (amount0Out > 0) _safeTransfer(_token0, to, amount0Out); // 先乐观地转出代币
        if (amount1Out > 0) _safeTransfer(_token1, to, amount1Out); // 先乐观地转出代币
        if (data.length > 0) IUniswapV2Callee(to).uniswapV2Call(msg.sender, amount0Out, amount1Out, data);
        balance0 = IERC20(_token0).balanceOf(address(this));
        balance1 = IERC20(_token1).balanceOf(address(this));
    }
    // ...随后核算输入是否足够（见下文）
```

调用者（通常是 Router）在调用 `swap` 之前，已经把要付出的输入代币转入了 Pair。因此当 `swap` 开始执行时，Pair 的余额里既包含原有的储备量，也包含这笔输入。`swap` 直接把 `amount0Out`/`amount1Out` 数量的输出代币转给 `to`，再去检查余下的事情。

注意这里 `amount0Out` 与 `amount1Out` 至少有一个大于 0，但不能同时为输入方向，具体用哪个代币换哪个，完全由调用者通过这两个参数指定，合约本身不关心方向。

#### 反推实际输入

转出输出代币后，合约重新读取余额，反推出实际收到了多少输入代币：

```solidity
uint amount0In = balance0 > _reserve0 - amount0Out ? balance0 - (_reserve0 - amount0Out) : 0;
uint amount1In = balance1 > _reserve1 - amount1Out ? balance1 - (_reserve1 - amount1Out) : 0;
require(amount0In > 0 || amount1In > 0, 'UniswapV2: INSUFFICIENT_INPUT_AMOUNT');
```

以 token0 为例：若没有收到任何 token0 输入，转出 `amount0Out` 后余额应恰好是 `_reserve0 - amount0Out`。因此超出该值的部分就是实际收到的 token0 输入量 `amount0In`。普通交易里，被换入的代币 `amountIn > 0`，被换出的代币 `amountIn == 0`。

#### K 不变量检查

最关键的一步，是校验交易没有让资金池“缩水”。V2 采用了一个精巧的整数化写法：

```solidity
uint balance0Adjusted = balance0.mul(1000).sub(amount0In.mul(3));
uint balance1Adjusted = balance1.mul(1000).sub(amount1In.mul(3));
require(balance0Adjusted.mul(balance1Adjusted) >= uint(_reserve0).mul(_reserve1).mul(1000**2), 'UniswapV2: K');
```

这里的 `.mul(1000).sub(amount0In.mul(3))`，相当于从输入量中扣除了 $\frac{3}{1000} = 0.3\%$ 的手续费。校验条件展开后即：

$$(1000 \cdot \text{balance0} - 3 \cdot \text{amount0In})(1000 \cdot \text{balance1} - 3 \cdot \text{amount1In}) \ge 1000^2 \cdot \text{reserve0} \cdot \text{reserve1} \tag{3}$$

两边约去 $1000^2$，并代入 $\text{balance} \approx \text{reserve} + \text{amountIn} - \text{amountOut}$，其含义正是第 1 章公式 (2) 带手续费后的形式：

$$(x + 0.997 \cdot \Delta x)(y - \Delta y) \ge x \cdot y \tag{4}$$

也就是说，扣除 0.3% 手续费后，池子的乘积 $k$ 不允许下降，多出来的部分就是留存在池中的手续费，归所有 LP 所有（上一节 `burn` 用 `balance` 而非 `reserve` 提取，正是为了让 LP 分得这部分）。

这个链上校验与外围库 `UniswapV2Library.getAmountOut` 给出的链下估算是同一个公式的两种写法。后者把 0.3% 写成 $\frac{997}{1000}$：

$$\text{amountOut} = \frac{997 \cdot \text{amountIn} \cdot \text{reserveOut}}{1000 \cdot \text{reserveIn} + 997 \cdot \text{amountIn}} \tag{5}$$

Router 用它在链下算出预期输出、再做滑点保护；而链上 `swap` 用式 (3) 兜底，保证实际结果不会优于该公式允许的边界。

#### 完整流程

`swap` 的完整顺序可以归纳为：

1. 校验输出量非零且不超过储备量
2. **乐观转出**输出代币给 `to`
3. 若 `data` 非空，回调 `to` 的 `uniswapV2Call`（闪电兑换入口）
4. 重读余额，反推实际输入量 `amount0In`/`amount1In`
5. **K 不变量检查**：扣 0.3% 手续费后乘积不得下降
6. `_update` 同步储备量并累加预言机价格，emit `Swap`

值得注意的是，整个 `swap` 没有显式接收“输入量”参数，输入是从余额差反推的；也没有限定兑换方向，由 `amount0Out`/`amount1Out` 的非零项决定。这种“只看结果、不问过程”的设计，正是闪电兑换得以成立的必要条件。

### sync() 与 skim()

`sync` 和 `skim` 是 Pair 合约提供的两个工具函数，用于处理储备量与实际余额不同步的特殊情况。

#### sync：储备量同步到余额

```solidity
function sync() external lock {
    _update(
        IERC20(token0).balanceOf(address(this)),
        IERC20(token1).balanceOf(address(this)),
        reserve0,
        reserve1
    );
}
```

`sync` 将储备量强制更新为当前的实际余额。这在以下场景中有用：

- **转账扣费代币（fee-on-transfer tokens）**：某些代币在每次转账时会扣除一部分费用。当用户将这类代币转入 Pair 时，实际到账数量少于转入数量，导致余额与储备量不一致。调用 `sync` 可以修正这种偏差
- **意外转入**：如果有人误将代币直接转入 Pair 合约（不是通过 `mint`），这些代币不会被记录在储备量中。`sync` 可以将这些无主代币纳入储备量，惠及所有 LP
- **储备量修复**：当任何原因导致余额和储备量不同步时，`sync` 是最直接的修复手段

#### skim：余额溢出提取

```solidity
function skim(address to) external lock {
    address _token0 = token0;
    address _token1 = token1;
    _safeTransfer(_token0, to, IERC20(_token0).balanceOf(address(this)).sub(reserve0));
    _safeTransfer(_token1, to, IERC20(_token1).balanceOf(address(this)).sub(reserve1));
}
```

`skim` 是 `sync` 的逆操作：将实际余额中超出储备量的部分提取出来。它把 `balance - reserve` 的差额转给指定地址。

`skim` 的主要用途是**在调用 `mint` 或 `swap` 之前清理多余的余额**。因为 `mint`/`swap` 通过余额差来推断新增或输入代币数量，如果合约中已有“多余”的代币（比如之前有人误转入），这些代币会被错误地计入。先调用 `skim` 清理多余余额，再调用 `mint`/`swap`，可以确保正确的行为。

另一个用途是提取意外转入的代币。如果有人误将代币直接转入 Pair 合约，任何人都可调用 `skim` 将其提取，因为 `skim` 只提取超出储备量的部分，不会影响正常流动性。

#### sync 与 skim 的互补关系

| 操作 | 余额 > 储备量时 | 效果 |
|------|----------------|------|
| `sync` | 将溢出纳入储备量 | 多余代币归所有 LP |
| `skim` | 将溢出提取给指定地址 | 多余代币归调用者 |

两者都是将储备量与余额重新同步的手段，区别在于溢出部分归谁。`sync` 将溢出捐赠给所有 LP（通过增大储备量），而 `skim` 允许任何人取走溢出。

## 总结

本章深入了核心层的两大合约。Factory 以极简的状态掌管交易对的创建与协议费开关：双向 `getPair` 映射与 `allPairs` 列表构成交易对登记表，`feeTo`/`feeToSetter` 掌管协议费治理，合约没有 `owner`、也没有升级机制。`createPair` 先排序代币、做去重校验，再用 `create2`（盐为 `keccak256(token0 ‖ token1)`）部署 Pair 并双向登记；构造函数无参与 `initialize` 分离，使 `creationCode` 哈希成为常量，据此任何人可用 `pairFor` 反事实地算出 Pair 地址。Factory 几乎无法被任何人改动，核心规则的确定性即是它作为可信底层的根基。

Pair 的储备量与时间戳打包在单个存储槽，所有改变储备量的操作最终都经 `_update` 完成。添加流动性时，首次按 $\sqrt{\Delta x \cdot \Delta y}$ 计算并锁定 1000 个最小流动性，后续取两种代币算出的流动性中较小者；移除流动性时，LP 返还 LP Token、按余额占比取回代币。`swap` 先乐观转出输出代币，再从余额差反推实际输入，最后用扣 0.3% 手续费后的 K 不变量检查兜底；在转出与检查之间回调 `uniswapV2Call`，实现可在同一交易内借还的闪电兑换。`sync` 与 `skim` 处理储备量与余额不同步的边角情形。核心层的两大合约至此分析完毕，下一章起进入外围层。
