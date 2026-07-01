# V2 Overall Architecture

The Uniswap V2 contract codebase is divided into two layers:

- The core layer: carries only the most fundamental, immutable business logic.
- The periphery layer: encapsulates the interaction logic with the core-layer contracts.

This chapter sketches the responsibilities of these two layers and the roles of each contract at a high level, helping the reader first establish a global view. The internal implementation details of the contracts in each layer will be examined one by one in subsequent chapters.

> **Tip**
> This chapter is an overview. Beginners need not understand everything here right away — subsequent chapters will dissect all the details one by one.

## Overview

The Uniswap V2 contract codebase is split into two independent repositories:

- `v2-core` (the core layer). The core layer contains only the most fundamental, immutable business logic, such as trading, liquidity management, trading fees, and protocol fee calculation; it has no user-facing interfaces. A substantial portion of its code is a direct implementation of the formulas from Chapter 1. Once deployed, the core layer cannot be upgraded (with the exception of a few governance parameters), so it must keep the "absolutely must-not-be-wrong" logic minimal and rock-solid.
- `v2-periphery` (the periphery layer). The periphery contracts act as a "safety shell," encapsulating all the protective logic and convenience features needed for user interaction: _slippage protection_ ensures that the received amount is no less than an acceptable lower bound; _deadline checks_ prevent transactions from being mined late and executed at stale prices; _multi-hop routing_ supports completing an A→B→C swap through multiple trading pairs; and ETH/WETH wrapping lets users participate with native ETH.

![Two-layer architecture](images/ch03/architecture.png)

*Figure 1　The two-layer architecture of Uniswap V2. The periphery layer (Router, Migrator, and the libraries) encapsulates user interaction and safety checks, calling the core layer via libraries to complete swaps and liquidity operations; in the core layer, the Factory creates Pairs, and each Pair inherits `UniswapV2ERC20` to mint LP Tokens.*

The benefit of this design is that the two layers can evolve independently. Periphery contracts can be upgraded, replaced, or even coexist in multiple versions; the minimalism of the core layer also makes it a trustworthy foundation that can be reused by all kinds of periphery contracts and third-party protocols.

## Core-Layer Contracts

The core layer lives in the [v2-core](https://github.com/Uniswap/v2-core) repository and has three main logic contracts:

- `contracts/UniswapV2Factory.sol`　The Factory is the "registry" of the entire V2 system, responsible for creating trading pairs and registering their addresses: for any new token pair, it deploys a corresponding Pair contract and supports looking up an already-created Pair by token address. In addition, the Factory governs the _protocol fee_: it can designate the fee recipient address and the account authorized to change it; this mechanism (including why the protocol fee is disabled by default) will be elaborated in subsequent chapters.

- `contracts/UniswapV2Pair.sol`　Each Pair contract represents a trading pair and is the most central and complex contract in V2; the system has as many Pairs as there are trading pairs, each with completely isolated state. A Pair simultaneously plays two roles: it is an AMM pool that records the reserves of two tokens and performs swaps accordingly (including _flash swaps_, which can borrow and repay within the same transaction) and liquidity management; it is also an ERC20 token contract that mints _liquidity tokens (LP Tokens)_ to liquidity providers representing their share of the pool, for which it directly inherits from the `UniswapV2ERC20` described below. Furthermore, the Pair continuously accumulates the cumulative prices of the two tokens, providing raw data for the oracle. The specific implementation of these mechanisms will be dissected in subsequent chapters.

- `contracts/UniswapV2ERC20.sol`　This is a standard ERC20 implementation that the Pair contract directly inherits from; the LP Tokens received by liquidity providers are minted by it, representing their share of the pool. All Pairs share the same token name `Uniswap V2`, symbol `UNI-V2`, and 18 decimals, but each Pair is an independent instance maintaining its own supply and balances. In addition to standard transfers and approvals, it also implements _EIP-2612 permit_, allowing holders to complete an approval with a single off-chain signature, sparing a separate `approve` transaction.

Beyond these three contracts, the core layer also includes several interfaces and libraries that make contract boundaries clear and logic reusable. The interfaces define the public APIs exposed by the contracts:

- `contracts/interfaces/IUniswapV2Factory.sol`: The Factory's interface, declaring functions for pair creation, lookup, and protocol fee governance.
- `contracts/interfaces/IUniswapV2Pair.sol`: The Pair's interface, declaring functions for reading reserves, liquidity management, swaps, and the flash swap callback.
- `contracts/interfaces/IUniswapV2ERC20.sol`: The LP Token's interface, declaring standard ERC20 methods and `permit`.
- `contracts/interfaces/IUniswapV2Callee.sol`: Defines the callback function `uniswapV2Call` invoked during a swap — the very interface the Pair relies on to implement flash swaps; any contract that wishes to be called back during a swap must implement it.
- `contracts/interfaces/IERC20.sol`: The ERC20 interface used by the core layer when referencing external tokens.

The libraries hold no state and perform pure computation:

- `contracts/libraries/SafeMath.sol`: Provides overflow-safe arithmetic (`add`/`sub`/`mul`).
- `contracts/libraries/Math.sol`: Provides `min` (minimum) and `sqrt` (square root).
- `contracts/libraries/UQ112x112.sol`: The UQ112.112 fixed-point library introduced in Chapter 2, used for cumulative price calculations.

## Periphery-Layer Contracts

The periphery layer lives in the [v2-periphery](https://github.com/Uniswap/v2-periphery) repository and is the entry point users actually interact with. It is built on top of the core layer and contains no fundamental AMM logic itself; its centerpiece is the Router, along with a migration tool and several libraries.

- `contracts/UniswapV2Router01.sol`　The Router is the main entry point for users to interact with V2. It does not perform swap math itself; instead, it encapsulates the workflow of "preparing tokens, calling the Pair, and validating the result," layered with the safety checks and conveniences that the core layer deliberately omits: slippage protection, deadline checks, multi-hop routing, and ETH wrapping. Its interface is organized into three groups by function: adding and removing liquidity, swapping, and price queries for off-chain estimation.
- `contracts/UniswapV2Router02.sol`　Built on `Router01`, it adds support for _fee-on-transfer tokens_ and changes functions to be overridable for extensibility; new projects typically adopt `Router02` directly.

The periphery layer also provides several libraries:

- `contracts/libraries/UniswapV2Library.sol`: The most frequently used, responsible for token address sorting (`sortTokens`), deterministic Pair address computation (`pairFor`), reserve queries (`getReserves`), and forward/inverse swap amount estimation (`getAmountOut`/`getAmountIn` and their multi-hop versions `getAmountsOut`/`getAmountsIn`).
- `contracts/libraries/UniswapV2OracleLibrary.sol`: Oriented toward oracles, encapsulating the helper logic for reading a Pair's cumulative prices (`currentCumulativePrices`) — the foundation for building a _Time-Weighted Average Price (TWAP)_ oracle; its TWAP mechanism will be covered in subsequent chapters.
- `contracts/libraries/UniswapV2LiquidityMathLibrary.sol`: Used to estimate the token value corresponding to a unit of LP share, and can provide manipulation-resistant valuation combined with arbitrage considerations.

In addition, the repository's `contracts/examples/` directory includes example contracts for flash swaps, oracles, and swapping to a target price, for developer reference.

## Summary

Uniswap V2's contracts adopt a two-layer architecture. The core layer carries only the most fundamental, immutable business logic: the Factory acts as a registry that creates and registers trading pairs, and the Pair is both an AMM pool and an LP Token issuer (inheriting from `UniswapV2ERC20`), trading trustworthiness and reusability for minimalism and immutability. The periphery layer, built on top of the core, encapsulates user interaction: the Router layers the workflow of preparing tokens, calling the Pair, and validating the result together with conveniences such as slippage protection, deadline checks, multi-hop routing, and ETH wrapping; the libraries provide address derivation, amount-and-price estimation, and oracle helpers. The two layers each have their own responsibilities and can evolve independently: the periphery can be upgraded and coexist in multiple versions, while the core serves as a trustworthy foundation for all kinds of periphery contracts and third-party protocols.

With this global view established, subsequent chapters will start from the Pair's swaps and liquidity management, diving into each mechanism of the core layer one by one, before returning to the periphery layer to see how the Router and libraries provide convenience and protection on top of it.
