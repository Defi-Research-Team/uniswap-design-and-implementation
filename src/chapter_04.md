# Library Contracts

This chapter introduces two categories of library contracts in the Uniswap V2 core layer that are reused over and over. The first category is the math libraries, including SafeMath (which provides overflow-safe arithmetic), Math (which provides minimum and square root), and UQ112x112 (which encapsulates fixed-point operations). The second category is the ERC-20 contract that carries the LP Token, which extends the standard with EIP-2612 to support approval via off-chain signatures.

## Math Libraries

The Solidity version used when developing the V2 contracts was `0.5.16`, which has no built-in arithmetic overflow checks, so all addition, subtraction, and multiplication involving token amounts must be checked manually — otherwise catastrophic vulnerabilities arise. `SafeMath.sol` provides safe arithmetic operations: `add`/`sub` use a "result re-check" to detect overflow (a sum smaller than an addend means an overflow occurred; a difference larger than the minuend means an underflow occurred), while `mul` checks by "dividing back to see if it equals the original."

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

The `Math.sol` contract provides two basic math operations: minimum and square root.

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

`min(uint x, uint y)` returns the smaller of the two. `sqrt(uint y)` returns $\lfloor\sqrt{y}\rfloor$, the largest integer whose square does not exceed $y$.

`sqrt` computes the square root using the _Babylonian method_. Its mathematical essence is applying _Newton's method_ to the equation $f(x) = x^2 - y = 0$: draw a tangent line at the current guess $x_n$, and take its intersection with the horizontal axis as the next guess. From the Newton formula $x_{n+1} = x_n - f(x_n)/f'(x_n)$ we obtain the iteration

$$x_{n+1} = \frac{1}{2}\left(x_n + \frac{y}{x_n}\right) \tag{1}$$

Equation (1) is exactly the origin of `x = (y / x + x) / 2` in the code. This iteration has two properties that guarantee convergence. First, by the arithmetic-geometric mean inequality, $\frac{1}{2}(x_n + y/x_n) \ge \sqrt{x_n \cdot y/x_n} = \sqrt{y}$, so each new guess is never below $\sqrt{y}$. Second, when $x_n > \sqrt{y}$ we have $y/x_n < \sqrt{y} < x_n$, and their average is strictly less than $x_n$; the sequence is monotonically decreasing with a lower bound of $\sqrt{y}$, so it must converge to $\sqrt{y}$, and the convergence is quadratic (the number of correct digits roughly doubles with each step). Geometrically, $x_n$ and $y/x_n$ always sandwich $\sqrt{y}$ from both sides, and taking their average yields a tighter approximation.

For the integer implementation, division `y / x` truncates the fractional part, so all iteration values are integers. The initial guess is $x_0 = y/2 + 1$, which is a safe overestimate ( $x_0 \ge \sqrt{y}$ ) for $y > 3$. The loop uses `z` to record the previous round's guess and continues as long as the new `x` is strictly smaller; once `x >= z`, no further decrease is possible, the loop terminates, and the final `z` is returned as $\lfloor\sqrt{y}\rfloor$. The case $y \le 3$ is handled separately: $y = 0$ returns 0, otherwise 1.

`UQ112x112.sol` provides fixed-point operations. Chapter 2 already introduced the principles of fixed-point numbers; in V2, only division of a fixed-point number by a plain integer is needed.

```solidity
// v2-core/contracts/libraries/UQ112x112.sol

function encode(uint112 y) internal pure returns (uint224 z) {
    z = uint224(y) * Q112;       // Q112 = 2**112, left-shift 112 bits
}
function uqdiv(uint224 x, uint112 y) internal pure returns (uint224 z) {
    z = x / uint224(y);
}
```

## LP Token

When a liquidity provider deposits assets into a pool, Uniswap mints LP Tokens as receipts. Chapter 1 derived the quantity formula for LP Tokens in the theoretical section; this chapter focuses on its contract implementation: Uniswap adopts the ERC-20 standard and, combined with EIP-2612, extends the off-chain approval feature.

### ERC-20

ERC-20 is the oldest and most widely used token standard on Ethereum, defining the basic properties of a token (such as name, symbol, and decimals) as well as operations like transfer and approval. The specific interface can be found in the [ERC-20 standard][1]. Uniswap implements a standard-compliant contract `UniswapV2ERC20` as a base class, which the pool contract Pair inherits, thereby gaining the ability to mint and burn LP Tokens.

The following is the interface definition of the Uniswap ERC-20:

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

Apart from `DOMAIN_SEPARATOR`, `PERMIT_TYPEHASH`, `nonces`, and `permit` — the methods added for the permit extension — the remaining methods are identical to the ERC-20 standard.

The ERC-20 interface and implementation are both straightforward, so the conventional parts will not be belabored; we focus only on a few noteworthy details and optimizations.

The first is `using SafeMath for uint;` at the top of the contract. This is Solidity's `using ... for ...` directive: it attaches the SafeMath library's functions to the `uint` type, with the library function's first parameter (here `uint x`) provided by the calling object. Thus, throughout the contract, `x.add(y)`, `x.sub(y)`, and `x.mul(y)` are equivalent to `SafeMath.add(x, y)`, `SafeMath.sub(x, y)`, and `SafeMath.mul(x, y)`, allowing the overflow-safe arithmetic defined in the previous section to be used as naturally as a built-in operator everywhere. Since ERC-20 involves token-amount addition and subtraction everywhere, this single line gives every balance and allowance modification automatic overflow protection without manually writing library calls in each expression.

The second is the two internal functions `_mint` and `_burn`. The ERC-20 standard only specifies transfer and approval and does not include minting and burning; many ERC-20 implementations have a fixed total supply at deployment. But the LP Token supply must change with liquidity: minted when liquidity is added, burned when removed. To this end, `UniswapV2ERC20` extends these two functions:

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

`_mint` simultaneously increases `totalSupply` and the recipient's balance; `_burn` does the reverse, decreasing both. Each emits a `Transfer` event with `address(0)` as the counterparty — the universal ERC-20 convention that "transferring from the zero address means minting, and transferring to the zero address means burning." They are declared `internal`, so only the Pair contract that inherits `UniswapV2ERC20` can call them when adding and removing liquidity; external accounts cannot mint LP Tokens on their own. Note that both increments and decrements go through `.add`/`.sub` — the protection brought by `using SafeMath for uint` above.

Transfer and approval are conventional external methods, but `transferFrom` has one noteworthy optimization:

```solidity
function transferFrom(address from, address to, uint value) external returns (bool) {
    if (allowance[from][msg.sender] != uint(-1)) {
        allowance[from][msg.sender] = allowance[from][msg.sender].sub(value);
    }
    _transfer(from, to, value);
    return true;
}
```

When the allowance equals `uint(-1)` (since `uint` is an unsigned integer type, `uint(-1)` is the maximum value of uint, i.e., `2^256 - 1`), the function **skips the deduction** and transfers directly. This is an _infinite allowance_ convention: the user grants the maximum value once and can then be called any number of times without repeated `approve`s. Skipping the deduction both saves a storage write (less Gas) and avoids the inherently meaningless operation of "subtracting a little from the maximum."

## EIP-2612

One of ERC-20's most central capabilities is `transferFrom`: after a token holder (owner) authorizes a specified allowance to a third party (spender) — usually a smart contract, but it can also be an external account — the spender can directly draw from the owner's account up to the authorized amount. The flow is as follows:

1. The owner initiates an on-chain transaction calling `approve` to authorize `spender` for a specified token amount.
2. The spender initiates an on-chain transaction calling `transferFrom` to transfer.

This flow has the following limitations:

1. Two separate on-chain transactions — one from the owner and one from the spender — must be initiated to complete the entire flow.
2. The transfer must wait for the approval to complete; the two operations are split across two on-chain transactions with no synchronization guarantee (suppose the owner first submits an `approve` transaction and the spender then submits a `transferFrom` transaction; even if both are included in the same block, if `transferFrom` is ordered before `approve` by the miner, the transfer fails).

`UniswapV2ERC20` implements _EIP-2612 permit_, which allows the owner to complete the approval off-chain: the owner hands the approval information along with a signature to the spender, who can then complete both the approve and transferFrom operations in a single on-chain transaction.

The permit implementation flow is divided into two steps: off-chain signing and on-chain verification.

The first step is off-chain signing: based on EIP-712, the owner signs a structured message whose content is "authorize `spender` to use up to `value` before `deadline`." EIP-712 packs this message into a 32-byte _digest_, and what the owner actually signs is this digest. Its construction is identical to the `digest` recomputed in the contract's `permit`:

```solidity
bytes32 digest = keccak256(abi.encodePacked(
    '\x19\x01',
    DOMAIN_SEPARATOR,
    keccak256(abi.encode(PERMIT_TYPEHASH, owner, spender, value, nonces[owner]++, deadline))
));
```

Reading from the outside in, each element bears a security responsibility:

- **`\x19\x01`**: The EIP-191 starting bytes. `\x19` ensures this data is not valid RLP encoding and thus cannot be impersonated as an Ethereum transaction; the immediately following `\x01` indicates this is an EIP-712 structured-data signature.
- **`DOMAIN_SEPARATOR`**: The _domain separator_, hashed in the constructor from the token name, version number, chain ID, and this contract's address:

  ```solidity
  DOMAIN_SEPARATOR = keccak256(abi.encode(
      keccak256('EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)'),
      keccak256(bytes(name)),
      keccak256(bytes('1')),
      chainId,
      address(this)
  ));
  ```

  It binds the signature to "this contract on this chain," so that one signature cannot be replayed on a different chain or a different contract.
- **`keccak256(abi.encode(PERMIT_TYPEHASH, owner, spender, value, nonces[owner]++, deadline))`**: The message body hash. `PERMIT_TYPEHASH` is the type hash of the Permit structure, obtained from `keccak256('Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)')`, declaring the types and order of each field; after it, the `owner`, `spender`, `value`, `nonce`, and `deadline` of this approval are filled in sequence.
- **`nonces[owner]++`**: An incrementing counter specific to the owner, incremented after each successful `permit`. It guarantees that the same set of signature parameters can be used only once: even if a signature leaks, it cannot be replayed, because the next `nonce` will already be different.
- **`deadline`**: The timestamp marking the signature's expiry, checked on-chain via `require(deadline >= block.timestamp)`; if expired, the entire transaction reverts.

The owner uses their private key to produce an ECDSA signature of `digest`, obtaining the `(v, r, s)` triple, which together with the plaintext parameters `owner`, `spender`, `value`, and `deadline` is handed to the spender. The entire signing process takes place off-chain and consumes no Gas.

The second step is on-chain verification: after receiving the signature, the spender calls the `permit` method, submitting the signature and parameters. `permit` validates the signature's legitimacy (whether it is valid, whether it has expired, and whether it was indeed signed by the owner); if validation passes, it performs the approve operation, setting the allowance granted by `owner` to `spender` to `value`. The implementation of `permit` is as follows:

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

The verification in `permit` proceeds in three steps, each corresponding to one of the security guarantees described above. First, `require(deadline >= block.timestamp)` rejects expired signatures. Then the `digest` is recomputed the same way; note that `nonces[owner]++` here serves a dual purpose: it participates in the hash as the current value and increments the counter as a side effect. The contract reads the current `nonce` $N$, computes the digest with it, and verifies; once it passes, the `nonce` has already become $N+1$, and this set of signatures can no longer be used. Finally, `ecrecover(digest, v, r, s)` recovers the signer's address from the digest and signature, requiring it to be non-zero (ruling out the case where `ecrecover` returns the zero address for an invalid signature) and equal to the parameter `owner` — thereby proving that this authorization was indeed personally signed by the owner. After all three checks pass, `_approve(owner, spender, value)` writes the allowance, equivalent to the owner initiating an `approve` themselves; the only difference is that this approval is obtained with an off-chain signature, thereby saving an on-chain transaction.

## Summary

This chapter reviewed two categories of repeatedly-reused infrastructure in the V2 core layer. The three stateless math libraries each have their own responsibility: SafeMath provides overflow-safe `add`/`sub`/`mul` for all token-amount operations, given that Solidity `0.5.16` lacks built-in overflow checks; Math provides `min` (minimum) and `sqrt` (square root), where `sqrt` computes $\lfloor\sqrt{y}\rfloor$ based on the Babylonian method (an integer adaptation of Newton's method); and UQ112x112 is the on-chain encapsulation of the fixed-point numbers from Chapter 2. None of the three holds state — they perform pure computation and can be referenced by any contract without side effects.

The LP Token is carried by `UniswapV2ERC20`, which makes three extensions on top of the standard ERC-20: `using SafeMath for uint` provides automatic overflow protection for all arithmetic across the contract; the internal `_mint`/`_burn` fill in the minting and burning capabilities missing from the standard; and in `transferFrom`, the deduction is skipped for infinite allowances to save Gas. On top of this, the EIP-2612 permit is implemented, further trading a single off-chain EIP-712 signature for an on-chain approval, compressing the original two-transaction flow into one: the domain separator binds the chain and contract, `nonces` prevents replay, and `deadline` prevents expiry, while on-chain `ecrecover` recovers the signer's address to complete verification.

[1]: https://eips.ethereum.org/EIPS/eip-20
