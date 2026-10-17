
"""
CompilerMate Phase 3 — Demonstration Scenarios

This file contains realistic examples for each supported Python diagnostic
category. Open it in VS Code with the CompilerMate extension enabled.

To test a scenario:
1. Uncomment ONLY the code under that scenario.
2. Save the file.
3. Select the relevant diagnostic and invoke:
   CompilerMate: Investigate
4. Inspect the explanation, evidence, proposed diff, and verification.
5. Apply a fix only after reviewing it.

IMPORTANT:
Some scenarios intentionally introduce syntax errors. Enable one scenario
at a time, because an earlier syntax error may prevent later scenarios
from producing useful diagnostics.
"""

# =====================================================================
# Scenario 1: Unclosed Delimiter — Cause vs. Symptom
# Expected: The missing ']' on the first line causes the later syntax error.
# =====================================================================

def run_scenario_1():
    # Uncomment these three lines to test Scenario 1:
    numbers = [10, 20, 30
    def next_step():
        return 42
    pass


# =====================================================================
# Scenario 2: Missing Colon
# Expected: CompilerMate proposes adding ':' to the if statement.
# =====================================================================

def run_scenario_2(value: int):
    # Uncomment these two lines to test Scenario 2:
    # if value > 100
    #     print("Large value")
    pass


# =====================================================================
# Scenario 3: Expected Indented Block
# Expected: The function body needs an indented statement.
# =====================================================================

# Uncomment both lines below to test Scenario 3.
# def empty_worker_handler():
# print("Next handler")


# =====================================================================
# Scenario 4: Unterminated String Literal
# Expected: The string is missing its closing quote.
# =====================================================================

def run_scenario_4():
    # Uncomment these two lines to test Scenario 4:
    # welcome_banner = "Welcome to CompilerMate Phase 3
    # print(welcome_banner)
    pass


# =====================================================================
# Scenario 5: Undefined Name / Typographical Error
# Expected: 'record_cont' is a typo for the defined name 'record_count'.
# This scenario is valid Python syntax, so it can be tested without
# introducing a syntax error.
# =====================================================================

def run_scenario_5():
    record_count = 50

    # Uncomment the next line to test Scenario 5:
    # return record_cont + 10

    return record_count + 10


# =====================================================================
# Scenario 6: Unused Import
# Expected: A Python lint provider such as Pylance may report an unused
# import. CompilerMate can investigate only if it receives that diagnostic.
# =====================================================================

# Uncomment the next line to test Scenario 6:
# import os

# Uncomment this line too if you want to test an unused imported name:
# from math import sqrt, sin
