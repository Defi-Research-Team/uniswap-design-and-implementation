# 工具库合约

本章介绍 Uniswap V2 核心层中两类被反复复用的工具库合约。第一类是数学工具库，包括提供溢出安全算术的 SafeMath、提供取最小值与开平方的 Math，以及封装定点数运算的 UQ112x112；第二类是承载 LP Token 的 ERC-20 合约，它在标准之上扩展了 EIP-2612，支持以链下签名完成授权。

## 数学工具库

V2 合约开发时使用的 Solidity 版本为 `0.5.16`，该版本没有内建的算术溢出检查，因此所有涉及代币数额的加减乘都必须进行手动检查，否则将出现灾难性漏洞。`SafeMath.sol` 提供安全的算术运算，`add`/`sub` 利用“结果回检”判断溢出（和小于加数即上溢、差大于被减数即下溢），`mul` 则用“乘回去是否相等”来判断。

```solidity
// v2-core/contracts/libraries/SafeMath.sol

function add(uint x, uint y) internal pure returns (uint z) {
    require((z = x + y) >= x, 'ds-math-add-overflow');
}
function sub(uint x, uint y) internal pure returns (uint z) {
    require((z = x - y) <= x, 'ds-math-sub-underflow');
}
function mul(uint x, uint y) internal pure returns (uint z) {
    require(y == 0 || (z = x * y) / y == x, 'ds-math-mul-overflow');
}
```

`Math.sol` 合约提供两个基础数学运算：取最小值与开平方。

```solidity
// v2-core/contracts/libraries/Math.sol

function min(uint x, uint y) internal pure returns (uint z) {
    z = x < y ? x : y;
}

function sqrt(uint y) internal pure returns (uint z) {
    if (y > 3) {
        z = y;
        uint x = y / 2 + 1;
        while (x < z) {
            z = x;
            x = (y / x + x) / 2;
        }
    } else if (y != 0) {
        z = 1;
    }
}
```

`min(uint x, uint y)` 返回两者中较小者。`sqrt(uint y)` 返回 $\lfloor\sqrt{y}\rfloor$，即平方不超过 $y$ 的最大整数。

`sqrt` 用 _巴比伦开方法（Babylonian method）_ 求平方根。其数学本质是把 _牛顿迭代法（Newton's method）_ 作用于方程 $f(x) = x^2 - y = 0$：在当前猜测 $x_n$ 处作切线，取切线与横轴的交点作为下一个猜测，由牛顿公式 $x_{n+1} = x_n - f(x_n)/f'(x_n)$ 可得迭代式

$$x_{n+1} = \frac{1}{2}\left(x_n + \frac{y}{x_n}\right) \tag{1}$$

式 (1) 正是代码里 `x = (y / x + x) / 2` 的来历。该迭代有两条保证收敛的性质。其一，由算术-几何平均值不等式，$\frac{1}{2}(x_n + y/x_n) \ge \sqrt{x_n \cdot y/x_n} = \sqrt{y}$，故每个新猜测都不会低于 $\sqrt{y}$。其二，当 $x_n > \sqrt{y}$ 时 $y/x_n < \sqrt{y} < x_n$，两者的平均严格小于 $x_n$，序列单调递减且有下界 $\sqrt{y}$，故必然收敛到 $\sqrt{y}$，且收敛是二次的（每步有效位数大约翻倍）。几何上，$x_n$ 与 $y/x_n$ 总是从两侧夹住 $\sqrt{y}$，取平均便得到更紧的近似。

落到整数实现上，除法 `y / x` 会截断小数，迭代值始终为整数。初始猜测取 $x_0 = y/2 + 1$，它在 $y > 3$ 时是一个安全的过估（$x_0 \ge \sqrt{y}$）。循环用 `z` 记录上一轮的猜测，只要新一轮 `x` 严格更小就继续；一旦 `x >= z` 说明已不再下降，循环终止，返回最后的 `z` 即 $\lfloor\sqrt{y}\rfloor$。$y \le 3$ 的情形单独处理：$y = 0$ 返回 0，否则返回 1。

`UQ112x112.sol` 提供定点数运算。第 2 章已经介绍了定点数的原理，V2 中仅需用到定点数除以普通整数的除法。

```solidity
// v2-core/contracts/libraries/UQ112x112.sol

function encode(uint112 y) internal pure returns (uint224 z) {
    z = uint224(y) * Q112;       // Q112 = 2**112，左移 112 位
}
function uqdiv(uint224 x, uint112 y) internal pure returns (uint224 z) {
    z = x / uint224(y);
}
```

## LP Token

流动性提供者向资金池注入资产，Uniswap 铸造 LP Token 作为凭证。第 1 章理论部分推导了 LP Token 的数量公式，本章关注它的合约实现：Uniswap 采用 ERC-20 标准，并结合 EIP-2612 扩展了链下授权功能。

### ERC-20

ERC-20 是以太坊最古老也最广泛使用的代币标准，定义了代币的基本属性（如名称、符号、小数位数）以及转账、授权等操作，具体接口可查看 [ERC-20 标准][1]。Uniswap 实现了一份符合该标准的合约 `UniswapV2ERC20` 作为基类，资金池合约 Pair 继承它，从而获得铸造与销毁 LP Token 的能力。

以下是 Uniswap ERC-20 的接口定义：

```solidity
pragma solidity >=0.5.0;

interface IUniswapV2ERC20 {
    event Approval(address indexed owner, address indexed spender, uint value);
    event Transfer(address indexed from, address indexed to, uint value);

    function name() external pure returns (string memory);
    function symbol() external pure returns (string memory);
    function decimals() external pure returns (uint8);
    function totalSupply() external view returns (uint);
    function balanceOf(address owner) external view returns (uint);
    function allowance(address owner, address spender) external view returns (uint);

    function approve(address spender, uint value) external returns (bool);
    function transfer(address to, uint value) external returns (bool);
    function transferFrom(address from, address to, uint value) external returns (bool);

    function DOMAIN_SEPARATOR() external view returns (bytes32);
    function PERMIT_TYPEHASH() external pure returns (bytes32);
    function nonces(address owner) external view returns (uint);

    function permit(address owner, address spender, uint value, uint deadline, uint8 v, bytes32 r, bytes32 s) external;
}

```

除 `DOMAIN_SEPARATOR`、`PERMIT_TYPEHASH`、`nonces`、`permit` 这几个为 permit 扩展的方法外，其余方法与 ERC-20 标准一致。

ERC-20 的接口与实现都很简单，常规部分不再赘述，下面只关注几处值得注意的细节与优化。

第一处是合约顶部的 `using SafeMath for uint;`。这是 Solidity 的 `using ... for ...` 指令：它把 SafeMath 库的函数挂载到 `uint` 类型上，库函数的第一个参数（这里的 `uint x`）由调用对象充当。于是全合约范围内 `x.add(y)`、`x.sub(y)`、`x.mul(y)` 分别等价于 `SafeMath.add(x, y)`、`SafeMath.sub(x, y)`、`SafeMath.mul(x, y)`，使上一节定义的防溢出算术能像内置运算符一样自然地用在每一处。由于 ERC-20 处处涉及代币数额的加减，这一行让所有余额与授权的修改都自动获得溢出保护，无需在每个表达式里手写库调用。

第二处是 `_mint` 与 `_burn` 两个 internal 函数。标准 ERC-20 只规定转账与授权，并不包含增发与销毁，许多 ERC-20 实现的总供应量在部署时就固定不变。但 LP Token 的供应量必须随流动性增减：添加流动性时铸造、移除时销毁。为此 `UniswapV2ERC20` 扩展了这两个函数：

```solidity
// v2-core/contracts/UniswapV2ERC20.sol

function _mint(address to, uint value) internal {
    totalSupply = totalSupply.add(value);
    balanceOf[to] = balanceOf[to].add(value);
    emit Transfer(address(0), to, value);
}

function _burn(address from, uint value) internal {
    balanceOf[from] = balanceOf[from].sub(value);
    totalSupply = totalSupply.sub(value);
    emit Transfer(from, address(0), value);
}
```

`_mint` 同时增加 `totalSupply` 与接收者余额，`_burn` 反之同时扣减。两者都以 `address(0)` 作为对手方发出 `Transfer` 事件，这正是 ERC-20 中“从零地址转出即铸造、转入零地址即销毁”的通用约定。它们被声明为 `internal`，因此只有继承了 `UniswapV2ERC20` 的 Pair 合约才能在添加与移除流动性时调用，外部账户无法自行铸造 LP Token。注意两处自增自减都走 `.add`/`.sub`，正是前文 `using SafeMath for uint` 带来的保护。

转账与授权则是常规的外部方法，其中 `transferFrom` 有一处值得注意的优化：

```solidity
function transferFrom(address from, address to, uint value) external returns (bool) {
    if (allowance[from][msg.sender] != uint(-1)) {
        allowance[from][msg.sender] = allowance[from][msg.sender].sub(value);
    }
    _transfer(from, to, value);
    return true;
}
```

当授权额度等于 `uint(-1)`（由于 uint 是无符号整数类型，`uint(-1)` 为 uint 最大值，即 `2^256 - 1`）时，函数**跳过扣减**，直接转账。这是一种 _无限授权（infinite allowance）_ 约定：用户一次性授权最大值，之后便可被无限次调用而不必反复 `approve`。跳过扣减既省去一次存储写入（更省 Gas），也避免了“最大值减一点”这种本就无意义的运算。

## EIP-2612

ERC-20 最核心的能力之一是 transferFrom：当代币持有者 owner 授权指定额度给第三方 spender（通常是智能合约，也可以是外部账户）后，spender 可以直接从 owner 账户中动用不超过授权额度的代币。其流程如下：

1. owner 发起一笔链上交易，调用 `approve` 授权 `spender` 指定额度的代币。
2. spender 发起一笔链上交易，调用 `transferFrom` 转账。

上述流程存在以下局限性：

1. 必须分别由 owner 和 spender 前后发起两笔链上交易才能完成整个流程。
2. 转账必须等待授权完成，两个操作割裂在两笔链上交易中，没有任何同步性保证（假设 owner 先发起 `approve` 交易，spender 再发起 `transferFrom` 交易，两笔交易在同一个区块被打包，但是 `transferFrom` 交易被矿工打包在了 `approve` 交易之前，转账就会失败）。

`UniswapV2ERC20` 实现了 _EIP-2612 permit_，允许 owner 在链下完成授权：owner 把授权信息连同签名交给 spender，spender 即可在同一笔链上交易里完成 approve 和 transferFrom 操作。

permit 的实现流程分为链下签名与链上验证两步。

第一步是链下签名：owner 基于 EIP-712，对一条结构化消息签名，消息内容即“授权 `spender` 在 `deadline` 前使用不超过 `value` 的额度”。EIP-712 把这条消息打包成一个 32 字节的 _摘要（digest）_，owner 实际签的正是这个摘要。它的构造与合约中 `permit` 重新计算的 `digest` 完全一致：

```solidity
bytes32 digest = keccak256(abi.encodePacked(
    '\x19\x01',
    DOMAIN_SEPARATOR,
    keccak256(abi.encode(PERMIT_TYPEHASH, owner, spender, value, nonces[owner]++, deadline))
));
```

自外向内看，每个元素都承担一项安全职责：

- **`\x19\x01`**：EIP-191 起始字节。`\x19` 保证这段数据不是合法的 RLP 编码，从而无法被冒充成一笔以太坊交易；紧跟的 `\x01` 标明这是 EIP-712 的结构化数据签名。
- **`DOMAIN_SEPARATOR`**：_域分隔符（domain separator）_，在构造函数里由代币名、版本号、链 ID 与本合约地址哈希而成：

  ```solidity
  DOMAIN_SEPARATOR = keccak256(abi.encode(
      keccak256('EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)'),
      keccak256(bytes(name)),
      keccak256(bytes('1')),
      chainId,
      address(this)
  ));
  ```

  它把签名绑定到“这条链上的这个合约”，使得一个签名无法被拿到别的链或别的合约上重放。
- **`keccak256(abi.encode(PERMIT_TYPEHASH, owner, spender, value, nonces[owner]++, deadline))`**：消息体哈希。`PERMIT_TYPEHASH` 是 Permit 结构的类型哈希，由 `keccak256('Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)')` 得到，声明了各字段的类型与顺序；其后依次填入本次授权的 `owner`、`spender`、`value`、`nonce`、`deadline`。
- **`nonces[owner]++`**：owner 专属的递增计数器，每次 `permit` 成功后自增。它保证同一组签名参数只能使用一次：即便签名泄露也无法被重放，因为下一次的 `nonce` 已经不同。
- **`deadline`**：签名有效期的时间戳，链上以 `require(deadline >= block.timestamp)` 校验，过期则整笔交易回滚。

owner 用私钥对 `digest` 作 ECDSA 签名，得到 `(v, r, s)` 三元组，连同 `owner`、`spender`、`value`、`deadline` 等明文参数一并交给 spender。整个签名过程在链下完成，不消耗任何 Gas。
第二步是链上验证：spender 拿到签名后调用 `permit` 方法，提交签名与参数，`permit` 中会校验签名合法性（是否有效，是否过期，是否确实是 owner 签署）；若校验通过，则执行 approve 操作，将 owner 授权给 `spender` 的额度设为 `value`。`permit` 的具体实现如下：

```solidity
function permit(address owner, address spender, uint value, uint deadline,
                uint8 v, bytes32 r, bytes32 s) external {
    require(deadline >= block.timestamp, 'UniswapV2: EXPIRED');
    bytes32 digest = keccak256(abi.encodePacked(
        '\x19\x01',
        DOMAIN_SEPARATOR,
        keccak256(abi.encode(PERMIT_TYPEHASH, owner, spender, value, nonces[owner]++, deadline))
    ));
    address recoveredAddress = ecrecover(digest, v, r, s);
    require(recoveredAddress != address(0) && recoveredAddress == owner, 'UniswapV2: INVALID_SIGNATURE');
    _approve(owner, spender, value);
}
```

`permit` 的验证分三步，每步对应一项前文所述的安全保证。首先 `require(deadline >= block.timestamp)` 拒绝过期签名。随后用同样的方式重新计算 `digest`，注意 `nonces[owner]++` 在此处一身兼两职：它既作为当前值参与哈希，又顺带把计数器自增。合约读到当前 `nonce` $N$，用它算出摘要并验证；一旦通过，`nonce` 已变为 $N+1$，这组签名便无法再次使用。最后 `ecrecover(digest, v, r, s)` 从摘要与签名反推出签署者地址，要求它非零（排除 `ecrecover` 对非法签名返回零地址的情形）且等于参数 `owner`，即证明这条授权确由 owner 亲笔签署。三项检查全部通过后，`_approve(owner, spender, value)` 写入授权额度，等价于 owner 自己发起了一笔 `approve`，区别仅在于这笔授权是用链下签名换来的，从而省下了一笔链上交易。

## 总结

本章梳理了 V2 核心层中两类被反复复用的基础设施。三个无状态数学库各司其职：SafeMath 在 Solidity `0.5.16` 没有内建溢出检查的前提下，为所有代币数额运算提供防溢出的 `add`/`sub`/`mul`；Math 提供取最小值 `min` 与开方 `sqrt`，`sqrt` 基于巴比伦开方法（牛顿迭代法的整数化）求 $\lfloor\sqrt{y}\rfloor$；UQ112x112 则是第 2 章定点数的链上封装。三者都不持有状态、只做纯计算，可被任意合约无副作用地引用。

LP Token 由 `UniswapV2ERC20` 承载，它在标准 ERC-20 之上做了三处扩展：用 `using SafeMath for uint` 为全合约算术自动提供溢出保护，以 internal 的 `_mint`/`_burn` 补齐标准缺失的增发与销毁能力，并在 `transferFrom` 中对无限授权跳过扣减以节省 Gas。在此之上实现的 EIP-2612 permit，进一步用一笔链下 EIP-712 签名换取链上授权，把原本两笔交易的流程压缩为一笔：靠域分隔符绑定链与合约、靠 `nonces` 防重放、靠 `deadline` 防过期，链上再用 `ecrecover` 反推签署者地址完成验签。

[1]: https://eips.ethereum.org/EIPS/eip-20
