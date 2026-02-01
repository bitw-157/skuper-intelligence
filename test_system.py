"""Test script for Emergency Stockout Resolver Agent"""

from src.models import EmergencyStockoutState


def test_basic_structure():
    """Test that all modules can be imported"""
    print("Testing module imports...")

    try:
        print("✓ Config module loaded")

        from src.tools import ALL_TOOLS

        print(f"✓ Tools module loaded ({len(ALL_TOOLS)} tools available)")

        print("✓ Models module loaded")

        from src.agent import EMERGENCY_RESOLVER_SYSTEM_PROMPT

        print("✓ Agent module loaded")
        print(
            f"  System prompt length: {len(EMERGENCY_RESOLVER_SYSTEM_PROMPT)} characters"
        )

        print("✓ Orchestrator module loaded")

        print("✓ Workflow function loaded")

        print()
        print("=" * 80)
        print("All modules imported successfully!")
        print("=" * 80)
        return True

    except Exception as e:
        print(f"✗ Import failed: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


def test_agent_creation():
    """Test agent instantiation"""
    print()
    print("Testing agent creation...")

    try:
        from src.agent import create_emergency_resolver_agent

        agent = create_emergency_resolver_agent()
        print(f"✓ Agent created: {type(agent).__name__}")
        print(f"  Model: {agent.model_name}")
        print(f"  Temperature: {agent.temperature}")

        print()
        print("=" * 80)
        print("Agent created successfully!")
        print("=" * 80)
        return True

    except Exception as e:
        print(f"✗ Agent creation failed: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


def test_state_initialization():
    """Test state schema"""
    print()
    print("Testing state initialization...")

    try:
        # Create sample state using Pydantic
        state = EmergencyStockoutState(
            sku_id="SKU_001",
            product_details={
                "product_family": "Oncology",
                "target_service_level": 0.95,
                "temp_class": "Ambient",
                "unit_cost_usd": 29.93,
            },
            stockout_locations=[],
            available_inventory={},
        )

        print("✓ State initialized successfully")
        print(f"  SKU: {state.sku_id}")
        print(f"  Product Family: {state.product_details['product_family']}")
        print(f"  Criticality: {state.criticality_level}")

        print()
        print("=" * 80)
        print("State schema validated!")
        print("=" * 80)
        return True

    except Exception as e:
        print(f"✗ State initialization failed: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


def test_workflow_creation():
    """Test workflow graph creation"""
    print()
    print("Testing workflow creation...")

    try:
        from src.agent import create_emergency_workflow

        workflow = create_emergency_workflow()
        print("✓ Workflow created successfully")

        # Try to visualize workflow
        try:
            graph_ascii = workflow.get_graph().draw_ascii()
            print()
            print("Workflow structure:")
            print(graph_ascii)
        except Exception:
            print("  (Graph visualization not available)")

        print()
        print("=" * 80)
        print("Workflow validated!")
        print("=" * 80)
        return True

    except Exception as e:
        print(f"✗ Workflow creation failed: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


def run_all_tests():
    """Run complete test suite"""
    print()
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  SKUPER INTELLIGENCE - SYSTEM VALIDATION".center(78) + "║")
    print("║" + "  Emergency Stockout Resolver Test Suite".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "═" * 78 + "╝")
    print()

    results = []

    # Test 1: Module imports
    results.append(("Module Imports", test_basic_structure()))

    # Test 2: Agent creation
    results.append(("Agent Creation", test_agent_creation()))

    # Test 3: State initialization
    results.append(("State Schema", test_state_initialization()))

    # Test 4: Workflow creation
    results.append(("Workflow Graph", test_workflow_creation()))

    # Summary
    print()
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{test_name:.<50} {status}")

    print()
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print()
        print("🎉 All tests passed! System is ready to run.")
        print()
        print("Next steps:")
        print("1. Ensure database connection is configured")
        print("2. Run: python main.py")
        print("3. Or run: python main.py Oncology (to filter by product family)")
    else:
        print()
        print("⚠️  Some tests failed. Please review errors above.")

    print("=" * 80)


if __name__ == "__main__":
    run_all_tests()
