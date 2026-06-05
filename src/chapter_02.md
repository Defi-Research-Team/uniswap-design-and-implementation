# Fixed-Point Numbers

In the previous chapter, we established the mathematical framework for AMMs. Before diving into Uniswap's contract source code, we need to address a fundamental engineering issue: **Solidity has no floating-point numbers**.

This means we cannot directly use decimals in contracts to represent prices, exchange rates, and other values. For example, ETH's price might be 2000.5 USDC, but Solidity can only handle integers. Uniswap needs to perform precise price calculations in a pure integer environment — this is the problem that fixed-point number arithmetic solves.

This chapter focuses on the theoretical foundations of fixed-point numbers: why they're needed, the principles of Q number format, arithmetic rules, and how the specific formats adopted by Uniswap embody these principles. Once you understand these fundamental concepts, you'll be able to easily follow the fixed-point arithmetic logic in each Uniswap version's contract implementations covered in subsequent chapters.

## The Problem: Solidity Has No Floating-Point Numbers

Solidity currently does not support floating-point types (`float` / `double`). All on-chain arithmetic operations are integer operations, which means:

- Cannot directly represent values like `2000.5`
- Integer division truncates the decimal part: `5 / 2 = 2` (not 2.5)
- Price, exchange rate, and ratio calculations involving decimals all require special handling

Faced with this constraint, there are three common approaches:

| Approach | Idea | Example |
|------|------|------|
| Scale units | Use larger units to avoid decimals | Wei (1 ETH = 10¹⁸ Wei) |
| Rational representation | Numerator/denominator form | Reserve ratio directly expressed as reserve0 / reserve1 |
| Fixed-point numbers | Use fixed-bit-width integers to simulate decimals | Precise values for prices, square root prices, etc. |

**Scaling units** can solve the representation of magnitudes like ETH/USDC (using Wei instead of ETH), but cannot solve the precise calculation of price ratios — for example, how much ETH equals 1 USDC. This ratio can be very small (e.g., 0.0005), and simply scaling units makes it difficult to represent precisely.

**Rational representation** works in some scenarios, but when prices need to be stored and computed in contracts (rather than immediately calculating a ratio), a single numeric form is more convenient.

**Fixed-point numbers** are the core approach adopted by Uniswap. The idea is straightforward: use an integer where certain binary bits represent the integer part and the remaining bits represent the fractional part.

## Q Number Format

### Basic Concept

The standard notation for fixed-point numbers is the **Q format**, written as Qm.n, where:
- **m** is the number of bits for the integer part (excluding the sign bit)
- **n** is the number of bits for the fractional part

For unsigned fixed-point numbers, UQm.n is commonly used.

A Qm.n fixed-point number is essentially an integer whose stored value equals the actual value multiplied by $2^n$ (i.e., the number of fractional bits determines the scaling factor).

```
┌─────────────────────────────────┬─────────────────────────────────┐
│      Integer part (m bits)      │      Fractional part (n bits)   │
└─────────────────────────────────┴─────────────────────────────────┘
```

For example, to represent the actual value `1.5` in Q64.96 format:
- The scaling factor is $2^{96}$
- Stored value = $\lfloor 1.5 \times 2^{96} \rfloor$
- Binary representation: integer part is `1`, fractional part is `.1` (i.e., 0.5)

### Encoding and Decoding

**Encoding** (converting an actual value to a fixed-point number):

$$\text{encoded} = \lfloor \text{value} \times 2^n \rfloor$$

In Solidity, this is equivalent to left-shifting the integer value by $n$ bits:

```solidity
// Encoding: convert integer y to Qn format fixed-point number
uint256 encoded = uint256(y) << n;  // equivalent to y * 2^n
```

**Decoding** (converting a fixed-point number back to an actual value):

$$\text{value} = \frac{\text{encoded}}{2^n}$$

In Solidity, this is equivalent to right-shifting the fixed-point number by $n$ bits (if only the integer part is needed):

```solidity
// Decoding: extract integer part from Qn format fixed-point number
uint256 integerValue = encoded >> n;  // equivalent to encoded / 2^n
```

Note that right-shifting truncates the fractional part. If higher precision is needed, you can continue operating in fixed-point form and only decode when displaying the final result.

### Precision and Range

The Q format faces a **trade-off between range and precision**:

- **More integer bits** → larger representable value range, but lower fractional precision
- **More fractional bits** → higher fractional precision, but smaller value range

When the total number of bits is fixed (e.g., Solidity's `uint256`, `uint160`, `uint128`, etc.), a trade-off must be made between the two.

**Precision** is determined by the number of fractional bits. The minimum representable unit (precision) of the Qn format is $2^{-n}$, meaning the smallest distinguishable difference is $1/2^n$.

**Range** is determined by the number of integer bits. The unsigned representation range of the Qm.n format is $[0, 2^m - 2^{-n}]$, with the maximum representable integer value being $2^m - 1$.

Using several formats adopted by Uniswap as examples:

| Format | Total Bits | Scaling Factor | Integer Range | Fractional Precision |
|------|--------|---------|---------|---------|
| UQ112.112 | 224 | $2^{112}$ | $[0, 2^{112}-1]$ | $\approx 1.93 \times 10^{-34}$ |
| UQ64.96 | 160 | $2^{96}$ | $[0, 2^{64}-1]$ | $\approx 1.26 \times 10^{-29}$ |
| UQ128.128 | 256 | $2^{128}$ | $[0, 2^{128}-1]$ | $\approx 2.94 \times 10^{-39}$ |

As you can see, even with only 96 fractional bits, the precision reaches the $10^{-29}$ level — more than sufficient for financial calculations.

### Concrete Effect of Precision

Let's use the UQ64.96 format as an example to get an intuitive feel for the precision of 96 fractional bits.

Suppose the price of ETH is 2000 USDC, and the corresponding $\sqrt{P} = \sqrt{2000} \approx 44.7213595499958$.

In UQ64.96 format:

$$\sqrt{P}_{\text{encoded}} = \lfloor 44.7213595499958 \times 2^{96} \rfloor = 3544233733328802452386847$$

Decoding back:

$$\sqrt{P}_{\text{decoded}} = \frac{3544233733328802452386847}{2^{96}} \approx 44.721359549995796$$

Compared to the original value, the error is on the order of $10^{-15}$ — completely sufficient for on-chain price calculations.

The actual price $P$ is recovered by squaring $\sqrt{P}$:

$$P = \left(\frac{\sqrt{P}_{\text{encoded}}}{2^{96}}\right)^2 = \frac{\sqrt{P}_{\text{encoded}}^2}{2^{192}}$$

This recovery process involves multiplication of fixed-point numbers, which we analyze in detail below.

## Arithmetic Rules

The core challenge of fixed-point arithmetic is: **all operations are still performed in the integer domain, but the correct scaling relationships must be maintained**.

### Addition and Subtraction

Adding or subtracting two fixed-point numbers of the same format yields a result that is still a fixed-point number of the same format, with no additional processing needed:

```solidity
// Addition: Qn + Qn = Qn
uint256 sum = a + b;

// Subtraction: Qn - Qn = Qn
uint256 diff = a - b;
```

This is because the scaling factor $2^n$ naturally remains consistent in addition and subtraction: $(a \times 2^n) \pm (b \times 2^n) = (a \pm b) \times 2^n$.

Note overflow checking. In Solidity 0.8+, `uint256` arithmetic operations check for overflow by default.

### Multiplication

When two Qn format fixed-point numbers are multiplied, the scaling factor of the result becomes $2^{2n}$, and it must be divided by $2^n$ (i.e., right-shifted by $n$ bits) to restore the original format:

$$a_{\text{Qn}} \times b_{\text{Qn}} = (a \times 2^n) \times (b \times 2^n) = a \times b \times 2^{2n}$$

Dividing by $2^n$ to restore Qn format: $a \times b \times 2^{2n} / 2^n = a \times b \times 2^n$.

```solidity
// Multiplication: Qn × Qn → right-shift n bits to restore format
uint256 product = (a * b) >> n;  // equivalent to a * b / 2^n
```

**Problem**: The intermediate product $a \times b$ may overflow the `uint256` range.

**A common but imperfect approach**: Divide first, then multiply — `a * (b >> n)` or `(a >> n) * b`. But this performs right-shift truncation first, losing precision.

**The correct approach**: Use wide multiplication (e.g., 512-bit intermediate precision) to ensure the product doesn't overflow while not losing precision. Uniswap's `FullMath` library implements this full-precision multiplication, which will be analyzed in detail in the V3 chapters.

### Multiplying by an Integer

A fixed-point number multiplied by a regular integer yields a fixed-point number of the same format, with no scaling adjustment needed:

$$a_{\text{Qn}} \times b_{\text{int}} = (a \times 2^n) \times b = (a \times b) \times 2^n$$

```solidity
// Fixed-point × integer → direct multiplication
uint256 result = fixedPointA * integerB;
```

This is the simplest form of multiplication. Note that the result may overflow.

### Division

When two Qn format fixed-point numbers are divided, the scaling factor of the result becomes $2^0 = 1$ (i.e., it becomes a regular integer), and it must be multiplied by $2^n$ (i.e., left-shifted by $n$ bits) to restore the format:

$$\frac{a_{\text{Qn}}}{b_{\text{Qn}}} = \frac{a \times 2^n}{b \times 2^n} = \frac{a}{b}$$

Multiply by $2^n$ to restore Qn format.

```solidity
// Division: Qn ÷ Qn → left-shift n bits to restore format
uint256 quotient = (a << n) / b;  // scale up the dividend first, then divide
```

**Key**: You must left-shift the dividend (scale up) before performing integer division. If you divide first and then shift, the fractional part will be truncated and lost.

### Fixed-Point Number Divided by an Integer

A fixed-point number divided by a regular integer yields a fixed-point number of the same format, with no scaling adjustment needed:

$$\frac{a_{\text{Qn}}}{b_{\text{int}}} = \frac{a \times 2^n}{b} = \left(\frac{a}{b}\right) \times 2^n$$

```solidity
// Fixed-point ÷ integer → direct division
uint256 result = fixedPointA / integerB;
```

Note that integer division truncates, but since the dividend is already a scaled fixed-point number, the precision loss from truncation is minimal.

### Arithmetic Rules Quick Reference

| Operation | Action | Scaling Factor Change |
|------|------|-------------|
| Qn ± Qn | Direct add/subtract | Unchanged (still $2^n$) |
| Qn × Qn | Product right-shifted by $n$ bits | $2^{2n} → 2^n$ |
| Qn × integer | Direct multiplication | Unchanged (still $2^n$) |
| Qn ÷ Qn | Dividend left-shifted by $n$ bits, then divide | $2^0 → 2^n$ |
| Qn ÷ integer | Direct division | Unchanged (still $2^n$) |

### A Complete Calculation Example

Suppose we perform the following calculations using UQ64.96 format (i.e., $n = 96$):

Given $\sqrt{P} \approx 44.72$ (corresponding to price $P \approx 2000$) and liquidity $L = 1000000$.

**Encoding**:

$$\sqrt{P}_{\text{Q96}} = \lfloor 44.72 \times 2^{96} \rfloor = 3544233733328802452386847$$

**Calculate $\sqrt{P} \times L$** (fixed-point × integer):

This is fixed-point multiplied by an integer, so direct multiplication suffices:

$$\text{result} = \sqrt{P}_{\text{Q96}} \times L = 3544233733328802452386847 \times 1000000$$

The result is still in Q96 format.

**Calculate $\sqrt{P}^2$** (fixed-point × fixed-point):

Multiplying two Q96 numbers requires right-shifting by 96 bits:

$$\sqrt{P}^2_{\text{Q96}} = (\sqrt{P}_{\text{Q96}} \times \sqrt{P}_{\text{Q96}}) >> 96$$

This recovers price $P$ in Q96 format.

**Overflow issue**: $\sqrt{P}_{\text{Q96}} \times \sqrt{P}_{\text{Q96}}$ is the multiplication of two numbers approximately $3.5 \times 10^{24}$, resulting in approximately $1.26 \times 10^{49}$, well within `uint256`'s maximum value (approximately $1.16 \times 10^{77}$). However, when $\sqrt{P}$ is larger, the intermediate product may overflow — this is precisely why wide multiplication is needed.

## Implementation Patterns for Fixed-Point Numbers

### Solidity Patterns for Encoding and Decoding

Fixed-point encoding and decoding are the foundation of all operations. Here is a general implementation pattern:

```solidity
library FixedPoint {
    uint256 internal constant Q96 = 2 ** 96;  // scaling factor

    // Encoding: convert integer to Q96 fixed-point number
    function encode(uint256 value) internal pure returns (uint256) {
        return value * Q96;  // equivalent to value << 96
    }

    // Decoding: extract integer part from Q96 fixed-point number
    function decode(uint256 fixedValue) internal pure returns (uint256) {
        return fixedValue / Q96;  // equivalent to fixedValue >> 96
    }
}
```

Encoding uses multiplication (`value * Q96`) or the equivalent left-shift (`value << 96`); decoding uses division (`fixedValue / Q96`) or the equivalent right-shift (`fixedValue >> 96`).

### Implementation Patterns for Multiplication

Fixed-point multiplication is the most frequently used and error-prone operation. Different implementation strategies exist depending on the scenario.

**Pattern 1: Fixed-Point × Integer (Simple)**

```solidity
function mulUInt(uint256 fixedA, uint256 integerB) internal pure returns (uint256) {
    return fixedA * integerB;
    // Qn × int → Qn, no scaling adjustment needed
}
```

Be mindful of overflow: if both `fixedA` and `integerB` are large, the product may exceed `uint256` range.

**Pattern 2: Fixed-Point ÷ Integer (Simple)**

```solidity
function divUInt(uint256 fixedA, uint256 integerB) internal pure returns (uint256) {
    require(integerB > 0, "Division by zero");
    return fixedA / integerB;
    // Qn ÷ int → Qn, no scaling adjustment needed
}
```

**Pattern 3: Fixed-Point × Fixed-Point (Precision Protection Needed)**

This is the most complex scenario. There are two implementation strategies:

**Strategy A: Divide first, then multiply (saves gas, loses precision)**

```solidity
function mulNaive(uint256 fixedA, uint256 fixedB, uint8 n) internal pure returns (uint256) {
    return (fixedA >> n) * fixedB;  // right-shift n bits to shrink, then multiply
}
```

The right-shift truncates the lower $n$ bits of `fixedA`, introducing error.

**Strategy B: Full-precision multiplication (exact, higher gas)**

Store the product $a \times b$ using two 256-bit variables (512 bits total), then perform division on the 512-bit number, finally extracting the lower 256 bits as the result. This is the core approach used by Uniswap's `FullMath.mulDiv`, which will be analyzed in detail in the V3 chapters.

### Overflow Protection

When performing fixed-point arithmetic in Solidity, overflow is a concern that must be addressed. In particular:

- **Encoding overflow**: `value * Q96` may exceed the target type's range. For example, encoding a large integer as Q96 format to store in `uint160` requires ensuring `value * 2^96 < 2^{160}`
- **Arithmetic overflow**: Intermediate multiplication results may exceed the `uint256` range
- **Truncation overflow**: During type conversion (e.g., `uint256` → `uint160`), if the value exceeds the target type's range, the transaction must revert rather than silently truncate

Uniswap uses the `SafeCast` library to handle these issues. Its core pattern is: perform the conversion first, then check that the value is unchanged:

```solidity
function toUint160(uint256 y) internal pure returns (uint160 z) {
    require((z = uint160(y)) == y);  // if truncation occurred, z ≠ y, revert
}
```

This "convert first, validate after" pattern is both concise and safe.

## Design Considerations for Choosing Q Format

When selecting a Q format, the following factors should be considered:

### 1. Value Range Requirements

First determine the range of values that need to be represented. For example:
- ETH/USDC price might range from $10^{-6}$ (extreme case) to $10^{12}$
- The square root of the price has a smaller range, approximately the square root of the price
- The range of liquidity value $L$ depends on the pool's size

### 2. Precision Requirements

Financial calculations have strict precision requirements. The $10^{-29}$ precision provided by 96 fractional bits is sufficient to cover the vast majority of scenarios.

### 3. Storage Efficiency

Ethereum storage uses 256-bit (32-byte) slots. When choosing a fixed-point format, consider how to efficiently use storage space. For example:
- UQ64.96 totals 160 bits, which fits exactly in a `uint160`, consistent with Ethereum address length
- UQ112.112 totals 224 bits, requiring `uint224` storage

### 4. Compatibility with Other Data Types

Fixed-point formats typically need to work in conjunction with other contract data. For example:
- If reserves are stored as `uint112`, the fixed-point format should be chosen to work seamlessly with the scaling factor
- If the price square root is stored as `uint160`, Q64.96 is the natural choice

### 5. Intermediate Arithmetic Overflow

When choosing a format, you also need to consider whether intermediate values during computation will overflow. Multiplication is the most overflow-prone operation, and you need to ensure the intermediate product has sufficient space.

## Summary

- **The problem**: Solidity doesn't support floating-point types; all arithmetic operations are integer operations. Calculations involving decimals for prices, exchange rates, and ratios must be solved through fixed-point numbers
- **Q format**: Uses fixed-bit-width integers to simulate decimals. In Qm.n format, m bits represent the integer part and n bits represent the fractional part. Stored value = actual value × $2^n$
- **Precision and range**: The Q format faces a trade-off between precision and range. The 96-bit fractional precision ($10^{-29}$ level) adopted by Uniswap is more than sufficient for financial calculations
- **Arithmetic rules**: Addition/subtraction are direct operations; multiplication requires scaling adjustment (right-shift); division requires scaling up the dividend first (left-shift). Fixed-point × integer and fixed-point ÷ integer are the simplest forms
- **Overflow and precision**: Intermediate multiplication values may overflow `uint256`, requiring wide multiplication techniques to preserve precision; type conversions require safety checks to prevent silent truncation
- **Design considerations**: When choosing a Q format, consider value range requirements, precision requirements, storage efficiency, compatibility with other data, and intermediate arithmetic overflow risk

> **Reading Note**
> The fixed-point theory introduced in this chapter is the foundation for all subsequent contract analysis. In the V2 chapters, you'll see how the UQ112.112 format is used for cumulative price calculations; in the V3 chapters, you'll see how the UQ64.96 format represents the square root of price and how the FullMath library implements full-precision multiplication; in the V4 chapters, you'll see how these techniques continue to play a role in the new architecture. This chapter provides the necessary conceptual foundation for understanding these specific implementations.
