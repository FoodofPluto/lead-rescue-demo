from app import public_route_name


def test_form_lead_route_uses_customer_form_not_homepage():
    assert public_route_name("lead", None) == "customer_lead_form"
    assert public_route_name(None, None) == "homepage"
    assert public_route_name("lead", "1") == "operator"
