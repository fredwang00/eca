from eca.engine.waterfall import assess_waterfall, phase_x_status, StageResult


def _make_signals(**kwargs):
    """Build a minimal signals dict with defaults."""
    base = {
        "consumer_stress_tier": None,
        "credit_quality_trend": None,
        "auto_credit_trend": None,
        "housing_demand": None,
        "services_demand": None,
        "capex_direction": None,
        "pricing_power": None,
        "management_tone_shift": None,
        "signal_evidence": {},
    }
    base.update(kwargs)
    return base


def _make_facts(ticker, signals):
    return {ticker: {"signals": signals}}


def test_healthy_when_no_signals():
    facts = {"WMT": {"signals": _make_signals(
        consumer_stress_tier="neutral",
        pricing_power="strong",
        management_tone_shift="consistent",
    )}}
    stages = assess_waterfall(facts)
    assert all(not s.firing for s in stages)
    is_px, firing, total = phase_x_status(stages)
    assert not is_px
    assert firing == 0


def test_stage1_discretionary_cuts():
    facts = {
        "TGT": {"signals": _make_signals(
            consumer_stress_tier="trade_down",
            pricing_power="moderate",
        )},
        "ABNB": {"signals": _make_signals(
            services_demand="softening",
            pricing_power="weak",
        )},
        "SHOP": {"signals": _make_signals(
            services_demand="stable",
            pricing_power="strong",
        )},
    }
    stages = assess_waterfall(facts)
    stage1 = [s for s in stages if s.id == "stage_1"][0]
    assert stage1.firing
    assert "TGT" in stage1.triggered_by
    assert "ABNB" in stage1.triggered_by
    assert stage1.count == "2/3"


def test_stage2_essential_trade_down():
    facts = {
        "WMT": {"signals": _make_signals(consumer_stress_tier="essentials_pressure")},
        "COST": {"signals": _make_signals(consumer_stress_tier="neutral")},
    }
    stages = assess_waterfall(facts)
    stage2 = [s for s in stages if s.id == "stage_2"][0]
    assert stage2.firing
    assert stage2.triggered_by == ["WMT"]


def test_stage3_credit_bridging():
    facts = {
        "COF": {"signals": _make_signals(credit_quality_trend="normalizing")},
        "JPM": {"signals": _make_signals(credit_quality_trend="deteriorating")},
        "AXP": {"signals": _make_signals(credit_quality_trend="stable")},
        "AFRM": {"signals": _make_signals(credit_quality_trend="improving")},
    }
    stages = assess_waterfall(facts)
    stage3 = [s for s in stages if s.id == "stage_3"][0]
    assert stage3.firing
    assert "COF" in stage3.triggered_by
    assert "JPM" in stage3.triggered_by
    assert stage3.count == "2/4"


def test_stage4_housing_stress():
    facts = {
        "OPEN": {"signals": _make_signals(housing_demand="softening")},
    }
    stages = assess_waterfall(facts)
    stage4 = [s for s in stages if s.id == "stage_4"][0]
    assert stage4.firing


def test_stage5_services_contraction():
    facts = {
        "UBER": {"signals": _make_signals(services_demand="softening")},
        "ABNB": {"signals": _make_signals(services_demand="contracting")},
        "SHOP": {"signals": _make_signals(services_demand="stable")},
    }
    stages = assess_waterfall(facts)
    stage5 = [s for s in stages if s.id == "stage_5"][0]
    assert stage5.firing
    assert stage5.count == "2/3"


def test_stage6_auto_defaults():
    facts = {
        "COF": {"signals": _make_signals(auto_credit_trend="normalizing")},
        "JPM": {"signals": _make_signals(auto_credit_trend="stable")},
    }
    stages = assess_waterfall(facts)
    stage6 = [s for s in stages if s.id == "stage_6"][0]
    assert stage6.firing
    assert stage6.triggered_by == ["COF"]


def test_stage7_subscription_churn_requires_both():
    """Stage 7 needs BOTH pricing_power AND tone_shift firing."""
    # Only tone shift — should NOT fire
    facts = {
        "NFLX": {"signals": _make_signals(
            pricing_power="strong",
            management_tone_shift="alarmed",
        )},
        "SPOT": {"signals": _make_signals(
            pricing_power="moderate",
            management_tone_shift="more_cautious",
        )},
    }
    stages = assess_waterfall(facts)
    stage7 = [s for s in stages if s.id == "stage_7"][0]
    assert not stage7.firing

    # Both conditions met for NFLX
    facts["NFLX"]["signals"]["pricing_power"] = "weak"
    stages = assess_waterfall(facts)
    stage7 = [s for s in stages if s.id == "stage_7"][0]
    assert stage7.firing
    assert "NFLX" in stage7.triggered_by


def test_phase_x_requires_5_stages_and_4_tickers():
    """Phase X needs 5+ stages firing AND 4+ distinct tickers."""
    facts = {
        "TGT": {"signals": _make_signals(consumer_stress_tier="trade_down", pricing_power="weak")},
        "ABNB": {"signals": _make_signals(consumer_stress_tier="essentials_pressure", services_demand="contracting", pricing_power="weak")},
        "WMT": {"signals": _make_signals(consumer_stress_tier="essentials_pressure")},
        "COF": {"signals": _make_signals(credit_quality_trend="deteriorating", auto_credit_trend="deteriorating")},
        "JPM": {"signals": _make_signals(credit_quality_trend="deteriorating", auto_credit_trend="deteriorating")},
        "OPEN": {"signals": _make_signals(housing_demand="contracting")},
        "UBER": {"signals": _make_signals(services_demand="contracting")},
        "SHOP": {"signals": _make_signals(services_demand="contracting", consumer_stress_tier="credit_bridging", pricing_power="capitulating")},
    }
    stages = assess_waterfall(facts)
    is_px, firing, total = phase_x_status(stages)
    assert firing >= 5
    assert is_px


def test_phase_x_blocked_by_insufficient_tickers():
    """Even with 5+ stages, need 4+ distinct tickers to declare Phase X."""
    # 3 tickers across enough stages to fire 5+:
    # Stage 1 (TGT, ABNB, SHOP, threshold 2): TGT + SHOP fire
    # Stage 2 (WMT, COST, threshold 1): WMT fires
    # Stage 3 (COF, JPM, AXP, AFRM, threshold 2): COF + JPM fire — but we only have 3 tickers
    # We need a different approach: use tickers that appear in many stages.
    #
    # TGT fires stage 1 (stress). SHOP fires stage 1 (pricing) + stage 5 (services).
    # ABNB fires stage 1 (stress) + stage 5 (services).
    # That's only 3 tickers across stages 1+5. Need more stages from same tickers.
    #
    # Easier approach: supply exactly 3 tickers that collectively trigger 5 stages.
    facts = {
        # TGT: triggers stage 1 (stress tier)
        "TGT": {"signals": _make_signals(consumer_stress_tier="essentials_pressure", pricing_power="weak")},
        # SHOP: triggers stage 1 (pricing) + stage 5 (services)
        "SHOP": {"signals": _make_signals(
            consumer_stress_tier="credit_bridging",
            services_demand="contracting",
            pricing_power="capitulating",
        )},
        # ABNB: triggers stage 5 (services)
        "ABNB": {"signals": _make_signals(services_demand="contracting", pricing_power="weak")},
        # WMT: triggers stage 2 (essential trade-down)
        "WMT": {"signals": _make_signals(consumer_stress_tier="essentials_pressure")},
        # OPEN: triggers stage 4 (housing)
        "OPEN": {"signals": _make_signals(housing_demand="contracting")},
        # COF: triggers stage 3 (credit) + stage 6 (auto)
        "COF": {"signals": _make_signals(credit_quality_trend="deteriorating", auto_credit_trend="deteriorating")},
        # JPM: triggers stage 3 (credit) + stage 6 (auto)
        "JPM": {"signals": _make_signals(credit_quality_trend="deteriorating", auto_credit_trend="deteriorating")},
    }
    stages = assess_waterfall(facts)
    is_px, firing, _ = phase_x_status(stages)
    # Should fire many stages but with enough tickers for Phase X
    assert firing >= 5
    assert is_px  # has enough tickers

    # Now use only 3 distinct tickers that still fire 5+ stages.
    # COF appears in stages 3+6, OPEN in stage 4, SHOP+ABNB in stages 1+5.
    # That's stages 1,3,4,5,6 = 5 stages, but only 4 tickers (COF, OPEN, SHOP, ABNB).
    # To get exactly 3 tickers, drop ABNB so stage 5 still fires via SHOP alone? No, threshold=2.
    # Use COF(3,6) + OPEN(4) + WMT(2) = 3 stages only. Not enough.
    # Trick: use 3 tickers across as many stages as possible.
    # COF: stage 3 (credit, need 2/4) — alone won't fire. JPM needed too.
    # Can't easily get 5 stages from 3 tickers due to thresholds.
    # Instead, test with a manually constructed StageResult list.
    from eca.engine.waterfall import StageResult as SR
    # 5 stages firing, but only 3 distinct tickers
    fake_stages = [
        SR("s1", "S1", True, ["A", "B"], {}, "2/3"),
        SR("s2", "S2", True, ["A"], {}, "1/2"),
        SR("s3", "S3", True, ["B", "C"], {}, "2/4"),
        SR("s4", "S4", True, ["C"], {}, "1/1"),
        SR("s5", "S5", True, ["A", "B"], {}, "2/3"),
        SR("s6", "S6", False, [], {}, "0/2"),
        SR("s7", "S7", False, [], {}, "0/2"),
    ]
    is_px_few, firing_few, _ = phase_x_status(fake_stages)
    assert firing_few == 5
    assert not is_px_few  # only 3 distinct tickers (A, B, C)


def test_regime_labels():
    # 0 stages = Healthy
    stages = [StageResult("s", "S", False, [], {}, "0/1") for _ in range(7)]
    _, firing, _ = phase_x_status(stages)
    assert firing == 0

    # 2 stages = Pre-stress
    stages[0] = StageResult("s1", "S1", True, ["A"], {}, "1/1")
    stages[1] = StageResult("s2", "S2", True, ["B"], {}, "1/1")
    _, firing, _ = phase_x_status(stages)
    assert firing == 2


def test_missing_signals_skipped():
    """Tickers without signals should not cause errors."""
    facts = {
        "WMT": {},  # no signals key
        "COST": {"signals": _make_signals(consumer_stress_tier="essentials_pressure")},
    }
    stages = assess_waterfall(facts)
    stage2 = [s for s in stages if s.id == "stage_2"][0]
    assert stage2.firing
    assert stage2.triggered_by == ["COST"]
