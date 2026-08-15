# Mereology-Oriented Programming (MOP) Example

This updated model incorporates formal Abstract State Machine (ASM) execution semantics (like the `par` block and `:=` synchronous assignment) applied to a mereological data structure.

```text
// ---------------------------------------------------------
// 1. ATOMS (Primitives with no smaller proper parts)
// ---------------------------------------------------------
atom ID: String
atom Money: Int

// ---------------------------------------------------------
// 2. FUSION (Building Wholes from Parts)
// ---------------------------------------------------------
part Wallet = ID + Money

// Disambiguating identical types using role parts
part SenderWallet = Wallet
part ReceiverWallet = Wallet

part Transfer = SenderWallet + ReceiverWallet + Money

// ---------------------------------------------------------
// 3. BEHAVIOR (ASM Rules over MOP Structures)
// ---------------------------------------------------------
// Rules define structural conditions and state transitions.
rule ProcessTransfer(target) {
    // Structural guard
    require Parthood(Transfer, target)
    
    let transferValue = Money(target)
    let sender        = SenderWallet(target)
    let receiver      = ReceiverWallet(target)
    
    if Money(sender) >= transferValue {
        // ASM Synchronous Update (:=). 
        // The right-hand side is evaluated against the current state.
        // The left-hand side is updated simultaneously at the tick boundary.
        par {
            Money(sender)   := Money(sender) - transferValue
            Money(receiver) := Money(receiver) + transferValue
        }
        print("Transferred " + transferValue + " successfully.")
    } else {
        print("Insufficient funds for " + ID(sender))
    }
}

// ---------------------------------------------------------
// 4. THE EXECUTION ENGINE (Programs and Agents)
// ---------------------------------------------------------
program Main {
    let alice = SenderWallet("Alice_ACC", 500)
    let bob   = ReceiverWallet("Bob_ACC", 100)
    let action1 = Transfer(alice, bob, 50)
    
    let charlie = SenderWallet("Charlie_ACC", 1000)
    let dave    = ReceiverWallet("Dave_ACC", 200)
    let action2 = Transfer(charlie, dave, 150)
    
    // ASM parallel execution block.
    // The engine evaluates these rules continuously. Because action1 and 
    // action2 are mathematically Disjoint, the compiler runs them safely
    // on separate hardware threads.
    par {
        ProcessTransfer(action1)
        ProcessTransfer(action2)
    }
}
```

### Key Incorporations from ASM:
1. **The `:=` Operator**: Explicitly distinguishes simultaneous, delayed updates from immediate memory mutation. In `par` blocks, `x := y` and `y := x` safely swap values without intermediate variables.
2. **`par` and `seq` Blocks**: Explicit scoping defines whether rules run concurrently (`par`) or sequentially (`seq`).
3. **Programs**: Execution is framed as a `program` block (similar to CoreASM) that drives the continuous evaluation of rules.
