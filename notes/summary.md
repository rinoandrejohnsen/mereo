# Mereology-Oriented Programming (MOP)

Mereology is the philosophical and formal logical study of part-whole relationships. In Mereology-Oriented Programming (MOP), the base computational unit is the **Part**, and the primary mechanism for building programs is **Fusion** (Composition). 

> **First-Order Principle:** *"Everything is a Part. Programs are constructed by defining how smaller Parts fuse together to form larger Wholes, and computation is the resolution of structural Overlap and Parthood."*

Here are the core mereological concepts translated into theoretical MOP code.

## 1. Atoms ($At(x)$)
In mereology, an atom is an entity with no proper parts. In MOP, these are the fundamental language primitives. They cannot be decomposed further.
```text
// Atoms have no smaller subdivisions
Part StringAtom = "Alice"
Part IntAtom = 30
```

## 2. Fusion / Sum ($x + y$)
Fusion is the mereological sum of parts. Two parts combine to create a Whole without wrappers or hierarchical object structures (Composition as Identity). The order of fusion does not matter (commutativity).
```text
// Fusing an Int and a String to create a User Whole
Part User = Fusion(StringAtom, IntAtom)

// Later, dynamically expanding the Whole
Part JobTitle = "Engineer"
Part Employee = Fusion(User, JobTitle) 
```

## 3. Parthood ($Pxy$)
Parthood asserts that X is a part of Y. Instead of using arbitrary dot-notation variable names (like `user.age`), we query the Whole for a specific Part. This naturally acts as dynamic type-checking and structural polymorphism.
```text
// Extracting data by querying for a Part's type
Part age = IntAtom(User)  // Returns 30

// Polymorphism: Greeter only requires that a StringAtom is a part of the input
func Greeter(target) {
    require Parthood(StringAtom, target)
    print("Hello, " + StringAtom(target))
}

Greeter(User)     // Works, StringAtom is a part of User
Greeter(Employee) // Works, StringAtom is a part of Employee
```

## 4. Proper Part ($PPxy$)
X is a proper part of Y if X is a part of Y, but X is not identical to Y. This distinguishes a sub-component from the entire object itself.
```text
// IntAtom is a Proper Part of User (it is part of User, but not the whole User)
assert ProperPart(IntAtom, User) == true

// A Part is always a part of itself (reflexivity)
assert Parthood(User, User) == true

// But it is NEVER a Proper Part of itself (irreflexivity)
assert ProperPart(User, User) == false
```

## 5. Overlap ($Oxy$)
Two entities overlap if they share a common part. In MOP, this is how systems communicate or share state. Instead of reference passing or global variables, parts structurally overlap in memory space.
```text
Part MessageQueue = Queue()

// Both systems fuse with the same Queue
Part SystemA = Fusion(MessageQueue, ModuleA)
Part SystemB = Fusion(MessageQueue, ModuleB)

// SystemA and SystemB Overlap. They interact purely through their shared part.
assert Overlap(SystemA, SystemB) == true 
```

## 6. Disjointness ($Dxy$)
Two entities are disjoint if they share absolutely no parts. In MOP, the compiler uses disjointness to mathematically guarantee memory safety and thread isolation. If two Wholes are disjoint, they can never affect each other's state.
```text
Part Thread1Task = Fusion(WorkerA, DatasetA)
Part Thread2Task = Fusion(WorkerB, DatasetB)

// If the tasks are Disjoint, they are guaranteed safe for parallel execution
if Disjoint(Thread1Task, Thread2Task) {
    execute_parallel(Thread1Task, Thread2Task)
}
```
