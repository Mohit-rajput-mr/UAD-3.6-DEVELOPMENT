"""The five Market graphs, drawn from an imported file rather than pasted in."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import market  # noqa: E402


def test_the_example_file_draws_all_five():
    series = market.parse(market.example())
    assert len(series) == len(market.CHARTS)
    assert {market.category_of(s) for s in series} == set(market.CHARTS)


def test_every_chart_the_specification_names_can_be_drawn():
    """B-1 gives the Market section five graph categories; each one has a key
    in the import file and a caption the report prints."""
    for category, (key, caption) in market.CHARTS.items():
        assert key and caption, category


def test_a_partial_file_draws_what_it_has():
    series = market.parse({"market_charts": {
        "price_trend": {"unit": "$", "points": [
            {"period": "2025-Q1", "value": 100}, {"period": "2025-Q2", "value": 120}]}}})
    assert [s.key for s in series] == ["price_trend"]


def test_the_wrapper_is_optional():
    bare = market.example()["market_charts"]
    assert len(market.parse(bare)) == 5


@pytest.mark.parametrize("bad,why", [
    ("not json at all", "valid JSON"),
    ({"market_charts": {}}, "none of the five"),
    ({"market_charts": {"price_trend": {"points": []}}}, "no points"),
    ({"market_charts": {"price_trend": {"points": [{"period": "Q1"}]}}}, "needs a"),
    ({"market_charts": {"price_trend": {"points": [
        {"period": "Q1", "value": "about six"}]}}}, "not a number"),
])
def test_a_file_that_cannot_be_drawn_says_why(bad, why):
    with pytest.raises(market.MarketDataError) as failed:
        market.parse(bad if isinstance(bad, str) else json.dumps(bad))
    assert why in str(failed.value)


def test_money_and_percents_survive_being_written_the_human_way():
    charts = market.parse({"market_charts": {"price_trend": {
        "unit": "$", "points": [{"period": "Q1", "value": "$540,000"},
                                {"period": "Q2", "value": "551000"}]}}})
    assert charts[0].plots[0].values == [540000.0, 551000.0]


def test_a_drawn_chart_is_an_svg_in_the_samples_own_palette():
    """The palette is not a house style: it is the one the D-1 charts use."""
    for chart in market.parse(market.example()):
        drawing = market.svg(chart)
        assert drawing.startswith("<svg") and drawing.endswith("</svg>")
        assert market.BLUE in drawing, chart.key
        if len(chart.plots) > 1:
            assert market.ORANGE in drawing or market.GREY in drawing, chart.key


def test_a_second_axis_and_its_labels_are_drawn_where_the_sample_has_them():
    chart = [c for c in market.parse(market.example())
             if c.key == "absorption_rate"][0]
    assert [p.axis for p in chart.plots] == ["left", "left", "right"]
    drawing = market.svg(chart)
    assert "9.00" in drawing, "the line's points are not labelled"
    assert market.GREY in drawing, "the supply line is not the sample's grey"


def test_a_legend_appears_only_where_there_is_more_than_one_series():
    charts = {c.key: c for c in market.parse(market.example())}
    assert "Count of Listings" in market.svg(charts["absorption_rate"])
    assert "Total" not in market.svg(charts["year_built_of_sales"])


def test_a_dotted_trend_line_stays_dotted():
    chart = [c for c in market.parse(market.example())
             if c.key == "median_days_on_market"][0]
    assert "stroke-dasharray" in market.svg(chart)


def test_the_axis_follows_the_data_rather_than_a_fixed_scale():
    small = market.parse({"market_charts": {"absorption_rate": {"points": [
        {"period": "Q1", "value": 2}, {"period": "Q2", "value": 4}]}}})[0]
    large = market.parse({"market_charts": {"absorption_rate": {"points": [
        {"period": "Q1", "value": 2000}, {"period": "Q2", "value": 4000}]}}})[0]
    assert "4,000" in market.svg(large) or "4000" in market.svg(large)
    assert "4,000" not in market.svg(small)


def test_an_axis_far_from_zero_is_drawn_in_around_its_data():
    """Price Trend runs 200,000 to 600,000 in the sample rather than starting
    at nought and wasting two thirds of the plot."""
    bottom, top, _step = market._scale([530000, 425000, 474000, 490000])
    assert bottom >= 300000 and top <= 600000


def test_series_must_line_up_with_the_periods():
    with pytest.raises(market.MarketDataError) as failed:
        market.parse({"market_charts": {"price_trend": {
            "periods": ["Q1", "Q2", "Q3"],
            "series": [{"name": "x", "values": [1, 2]}]}}})
    assert "line up" in str(failed.value)


def test_the_prompt_states_the_shape_it_wants_back():
    """The thing reading it is a language model, and the failure everyone hits
    is a file that is nearly right."""
    for key, _caption in market.CHARTS.values():
        assert key in market.PROMPT, key
    assert "JSON" in market.PROMPT
    assert "periods" in market.PROMPT and "series" in market.PROMPT
    assert '"axis": "right"' in market.PROMPT and '"dotted"' in market.PROMPT
    # the example the prompt shows must itself be importable
    start = market.PROMPT.index("{")
    end = market.PROMPT.rindex("}") + 1
    shape = market.PROMPT[start:end]
    assert "market_charts" in shape
