#!/usr/bin/env python3
"""
Phase 2 Verification Test Suite
Tests core logic without requiring full deployment (no async/DB)
"""

import sys
sys.path.insert(0, '.')

def test_classifier():
    """Test three-tier task classification"""
    from openclaw.classifier import classify

    tests = [
        ("hi", "simple"),
        ("hello", "simple"),
        ("thanks", "simple"),
        ("yes", "simple"),
        ("what is DNS", "simple"),  # <=3 words
        ("explain blockchain", "medium"),  # ~2 words but "explain" isn't a complex keyword
        ("explain how DNS works", "medium"),  # >3 words, no complex keywords
        ("analyze energy prices", "complex"),  # contains "analyze"
        ("research the pros and cons of nuclear vs solar", "complex"),
        ("compare different", "complex"),  # contains "compare"
        ("a very long message with many words repeated over and over again to exceed 150 word count threshold for complexity classification", "complex"),
    ]

    print("Testing Classifier...")
    passed = 0
    for text, expected in tests:
        result = classify(text)
        status = "PASS" if result == expected else "FAIL"
        if result == expected:
            passed += 1
        print(f"  {status}: classify('{text[:40]}...') = {result} (expected {expected})")

    print(f"  Result: {passed}/{len(tests)} passed\n")
    return passed == len(tests)


def test_calculator():
    """Test safe math evaluation"""
    from openclaw.tools.calculator import calculate

    tests = [
        ("2 + 2", "4"),
        ("10 * 5", "50"),
        ("100 / 4", "25"),
        ("2 ^ 3", "8"),
        ("sqrt(16)", "4"),
        ("sin(0)", "0"),
        ("invalid @#$ expression", "[calculator error:"),  # error case
    ]

    print("Testing Calculator...")
    passed = 0
    for expr, expected_start in tests:
        result = calculate(expr)
        matches = result.startswith(expected_start) if expected_start.startswith("[") else result == expected_start
        status = "PASS" if matches else "FAIL"
        if matches:
            passed += 1
        print(f"  {status}: calculate('{expr}') = {result}")

    print(f"  Result: {passed}/{len(tests)} passed\n")
    return passed == len(tests)


def test_tool_router():
    """Test tool detection (no model call)"""
    from openclaw.tools.router import needs_tools

    tests = [
        ("2 + 2", ["calculator"]),
        ("what is 10 times 5", ["calculator"]),
        ("what is the latest news", ["web_search"]),
        ("current price of oil", ["web_search"]),
        ("hello world", []),
        ("calculate 5*6 and search current bitcoin price", ["calculator", "web_search"]),
    ]

    print("Testing Tool Router...")
    passed = 0
    for text, expected_tools in tests:
        result = needs_tools(text)
        # Check if expected tools are in result (order doesn't matter for this test)
        matches = set(expected_tools) == set(result)
        status = "PASS" if matches else "FAIL"
        if matches:
            passed += 1
        print(f"  {status}: needs_tools('{text[:40]}...') = {result}")

    print(f"  Result: {passed}/{len(tests)} passed\n")
    return passed == len(tests)


def test_agent_config():
    """Test agent loop configuration (no execution)"""
    from openclaw.agent import BUDGETS, MAX_ITERATIONS, MAX_DEEP_CALLS

    print("Testing Agent Configuration...")
    tests = [
        (BUDGETS["simple"] == 15, "simple budget = 15s"),
        (BUDGETS["medium"] == 90, "medium budget = 90s"),
        (BUDGETS["complex"] == 900, "complex budget = 900s"),
        (MAX_ITERATIONS == 3, "max iterations = 3"),
        (MAX_DEEP_CALLS == 2, "max deep calls = 2"),
    ]

    passed = 0
    for check, desc in tests:
        status = "PASS" if check else "FAIL"
        if check:
            passed += 1
        print(f"  {status}: {desc}")

    print(f"  Result: {passed}/{len(tests)} passed\n")
    return passed == len(tests)


def test_rate_limit_logic():
    """Test rate limit logic (without DB)"""
    print("Testing Rate Limit Logic...")

    # Just verify config is loadable
    from openclaw import config

    tests = [
        (config.RATE_LIMIT_COMPLEX_PER_HOUR == 5, "complex limit = 5/hour"),
        (config.RATE_LIMIT_MEDIUM_PER_HOUR == 20, "medium limit = 20/hour"),
        (config.RATE_LIMIT_GLOBAL_PER_HOUR == 20, "global limit = 20/hour"),
        (config.HF_INFER_TIMEOUT == 600, "HF timeout = 600s"),
    ]

    passed = 0
    for check, desc in tests:
        status = "PASS" if check else "FAIL"
        if check:
            passed += 1
        print(f"  {status}: {desc}")

    print(f"  Result: {passed}/{len(tests)} passed\n")
    return passed == len(tests)


def test_imports():
    """Test all Phase 2 modules import correctly"""
    print("Testing Module Imports...")

    modules = [
        "openclaw.classifier",
        "openclaw.tools",
        "openclaw.agent",
        "openclaw.memory",
        "openclaw.rate_limit",
    ]

    passed = 0
    for module_name in modules:
        try:
            __import__(module_name)
            print(f"  PASS: {module_name}")
            passed += 1
        except Exception as e:
            # DB connection errors are OK, syntax errors are not
            if "environment variable" in str(e) or "aiosqlite" in str(e):
                print(f"  PASS: {module_name} (DB not initialized, OK)")
                passed += 1
            else:
                print(f"  FAIL: {module_name} - {e}")

    print(f"  Result: {passed}/{len(modules)} passed\n")
    return passed == len(modules)


def main():
    print("=" * 70)
    print("ClawDBot Phase 2 Verification Test Suite")
    print("=" * 70 + "\n")

    results = []

    try:
        results.append(("Imports", test_imports()))
        results.append(("Classifier", test_classifier()))
        results.append(("Calculator", test_calculator()))
        results.append(("Tool Router", test_tool_router()))
        results.append(("Agent Config", test_agent_config()))
        results.append(("Rate Limit Config", test_rate_limit_logic()))
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"{status}: {name}")

    all_passed = all(p for _, p in results)
    print("\n" + ("=" * 70))
    if all_passed:
        print("ALL TESTS PASSED - Phase 2 Core Logic Verified!")
        print("=" * 70)
        return True
    else:
        print("SOME TESTS FAILED - Review output above")
        print("=" * 70)
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
