from handa.sample_data.generate import SEED, generate_catalog


def _request(name: str) -> str:
    catalog = generate_catalog()
    return next(item["text"] for item in catalog["requests"] if item["id"] == name)


def test_catalog_is_fixed_seed_and_sized():
    first = generate_catalog()
    second = generate_catalog()
    assert first == second
    assert first["seed"] == SEED == 20261115
    assert len(first["recipes"]) == 40
    assert len(first["suppliers"]) == 6
    assert len(first["requests"]) == 6
    assert first["currency"] == "PHP"


def test_complete_brief_prices_and_logs_every_handoff(desk):
    view = desk.wait(desk.begin(_request("town-hall")))
    assert view["status"] == "pass"
    assert view["pricing"]["currency"] == "PHP"
    by_source = {(message["from_agent"], message["source"]) for message in view["agent_messages"]}
    assert ("intake", "llm") in by_source
    assert ("menu", "llm") in by_source
    assert ("pricing", "llm") in by_source
    assert ("inventory", "python") in by_source
    tools = [message["to_agent"] for message in view["agent_messages"] if message["source"] == "tool"]
    assert tools == ["submit_event", "search_recipes", "check_diet", "get_budget_per_head", "read_quote"]
    rice = next(line for line in view["menu"]["lines"] if line["recipe_id"] == "garlic_rice")
    assert rice["portions"] == 63


def test_missing_budget_interrupts_then_a_cost_down_pass_fits(desk):
    run_id = desk.begin(_request("debut-ask"))
    paused = desk.wait(run_id)
    assert paused["status"] == "awaiting_intake"
    assert "budget_php" in paused["missing"]
    desk.reply(run_id, {"budget_php": 80000})
    view = desk.wait(run_id)
    assert view["status"] == "pass"
    assert view["revision"] == 1
    assert view["pricing"]["quote_php"] < 80000
    assert "lechon_belly" not in {line["recipe_id"] for line in view["menu"]["lines"]}


def test_loop_cap_is_flagged_over_budget(desk):
    view = desk.wait(desk.begin(_request("too-small")))
    assert view["status"] == "over_budget"
    assert view["revision"] == 2
    assert view["pricing"]["gap_php"] > 0


def test_same_day_switches_supplier(desk):
    view = desk.wait(desk.begin(_request("same-day")))
    switched = {line["name"]: line["switched_from"] for line in view["procurement"]["lines"] if line.get("switched_from")}
    assert switched["Chicken"] == "balintawak"
    assert view["procurement"]["infeasible"] is False


def test_extra_guests_reruns_from_the_menu_only(desk):
    run_id = desk.begin(_request("town-hall"))
    before = desk.wait(run_id)
    desk.disrupt(run_id, "extra_guests")
    after = desk.wait(run_id)
    assert after["event"]["guests"] == before["event"]["guests"] + 15
    rice = next(line for line in after["menu"]["lines"] if line["slot"] == "rice")
    assert rice["portions"] == 79
    hops = [(message["from_agent"], message["to_agent"]) for message in after["agent_messages"]]
    assert hops.count(("intake", "menu")) == 1
    assert ("desk", "menu") in hops


def test_spoilage_reruns_inventory_not_the_menu(desk):
    run_id = desk.begin(_request("town-hall"))
    desk.wait(run_id)
    before_messages = len(desk.view(run_id)["agent_messages"])
    desk.disrupt(run_id, "spoilage")
    after = desk.wait(run_id)
    hops = [(message["from_agent"], message["to_agent"]) for message in after["agent_messages"]]
    assert hops[before_messages:][0] == ("desk", "inventory")
    assert hops.count(("intake", "menu")) == 1
    assert after["inventory"]["lines"]
    chicken = next(line for line in after["inventory"]["lines"] if line["ingredient_id"] == "chicken")
    assert chicken["on_hand"] == 0
