#include <stdio.h>
#include <stdlib.h>

// =========================================================
// 1. MOP: Structural Definitions (Compiled to flat structs)
// =========================================================

typedef enum { RED, GREEN } Color;

// "Lane" is the fusion of an ID, CarQueue, and a TrafficLight (Color).
// The compiler flattens this into contiguous memory.
typedef struct {
    const char* id;
    int car_queue;
    Color color;
} Lane;

// "Intersection" is the fusion of two Lanes
typedef struct {
    Lane ns;
    Lane ew;
} Intersection;

// The Universal State
// We use a Universe struct to hold everything.
typedef struct {
    Intersection intersection;
} Universe;


// =========================================================
// 2. ASM + MOP: Transition Rules
// =========================================================

void rule_manage_lights(const Universe* current, Universe* next) {
    const Lane* ns = &current->intersection.ns;
    const Lane* ew = &current->intersection.ew;
    
    // ASM Logic: Synchronous transitions
    if (ns->car_queue > ew->car_queue && ew->color == GREEN) {
        next->intersection.ew.color = RED;
        next->intersection.ns.color = GREEN;
    }
    
    if (ew->car_queue > ns->car_queue && ns->color == GREEN) {
        next->intersection.ns.color = RED;
        next->intersection.ew.color = GREEN;
    }
}

void rule_move_traffic(const Lane* current_lane, Lane* next_lane) {
    if (current_lane->color == GREEN && current_lane->car_queue > 0) {
        next_lane->car_queue -= 1; 
    }
    
    if (rand() % 2 == 0) {
        next_lane->car_queue += 1;
    }
}


// =========================================================
// 3. Execution Engine (The Main Loop)
// =========================================================
int main() {
    Universe state_A;
    Universe state_B;
    
    state_A.intersection.ns.id = "Main St (NS)";
    state_A.intersection.ns.car_queue = 5;
    state_A.intersection.ns.color = GREEN;
    
    state_A.intersection.ew.id = "1st Ave (EW)";
    state_A.intersection.ew.car_queue = 12;
    state_A.intersection.ew.color = RED;
    
    Universe* current = &state_A;
    Universe* next = &state_B;

    // Seed the random number generator for predictability
    srand(42);

    printf("Starting Simulation...\n");

    for (int tick = 1; tick <= 5; tick++) {
        // Step 1: Clone 'current' to 'next'
        *next = *current;
        
        // Step 2: Evaluate Rules
        rule_manage_lights(current, next);
        rule_move_traffic(&current->intersection.ns, &next->intersection.ns);
        rule_move_traffic(&current->intersection.ew, &next->intersection.ew);
        
        // Step 3: Swap buffers
        Universe* temp = current;
        current = next;
        next = temp;
        
        // Print the state
        printf("Tick %d: [NS: %5s, Q: %2d] | [EW: %5s, Q: %2d]\n", 
            tick,
            current->intersection.ns.color == GREEN ? "GREEN" : "RED", 
            current->intersection.ns.car_queue,
            current->intersection.ew.color == GREEN ? "GREEN" : "RED", 
            current->intersection.ew.car_queue
        );
    }

    return 0;
}
