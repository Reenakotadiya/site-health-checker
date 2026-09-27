import pytest

from site_health_checker.accessibility import RULES, audit_html, page_score


def page(body, head="<title>T</title>", lang=' lang="en"'):
    """A page that passes every check except whatever `body` adds."""
    return f"<!DOCTYPE html><html{lang}><head>{head}</head><body><h1>Main</h1>{body}</body></html>"


def rules(html):
    return [issue.rule for issue in audit_html(html)]


def test_clean_page_has_no_issues():
    html = page('<img src="a.png" alt="A cat"><a href="/x">Read more</a><button>Send</button>'
                '<label for="e">Email</label><input id="e" type="email"><h2>Section</h2><h3>Sub</h3>')
    assert rules(html) == []
    assert page_score([]) == 100


@pytest.mark.parametrize("img, flagged", [
    ('<img src="logo.png">', True),
    ('<img src="line.png" alt="">', False),              # decorative image, valid
    ('<img src="x.png" aria-hidden="true">', False),     # hidden from screen readers
    ('<img src="x.png" role="presentation">', False),
    ('<img src="x.png" alt="Chart of sales">', False),
])
def test_image_alt(img, flagged):
    assert ("image-alt" in rules(page(img))) is flagged


@pytest.mark.parametrize("form, flagged", [
    ('<input type="text" name="q">', True),
    ('<label for="q">Search</label><input id="q" type="text">', False),
    ('<label>Search <input type="text"></label>', False),     # wrapped in a label
    ('<input type="text" aria-label="Search">', False),
    ('<input type="hidden" name="token">', False),            # never visible
    ('<input type="submit" value="Go">', False),               # buttons label themselves
    ('<select name="country"><option>India</option></select>', True),
    ('<textarea name="message"></textarea>', True),
    ('<label for="other">X</label><input id="q">', True),     # label points somewhere else
])
def test_form_labels(form, flagged):
    assert ("form-label" in rules(page(form))) is flagged


@pytest.mark.parametrize("markup, rule, flagged", [
    ('<a href="/cart"></a>', "link-name", True),
    ('<a href="/cart"><img src="cart.svg"></a>', "link-name", True),
    ('<a href="/cart"><img src="cart.svg" alt="Cart"></a>', "link-name", False),
    ('<a href="/cart" aria-label="Cart"><svg></svg></a>', "link-name", False),
    ('<a href="/cart"><span>Cart</span></a>', "link-name", False),
    ('<a name="anchor"></a>', "link-name", False),              # not a link without href
    ('<button></button>', "button-name", True),
    ('<button><img src="x.svg"></button>', "button-name", True),
    ('<button aria-label="Close">×</button>', "button-name", False),
    ('<button>Save</button>', "button-name", False),
])
def test_link_and_button_names(markup, rule, flagged):
    assert (rule in rules(page(markup))) is flagged


def test_missing_page_language():
    assert "html-lang" in rules(page("", lang=""))
    assert "html-lang" in rules(page("", lang=' lang=""'))
    assert "html-lang" not in rules(page(""))


@pytest.mark.parametrize("viewport, flagged", [
    ("width=device-width, initial-scale=1", False),
    ("width=device-width, user-scalable=no", True),
    ("width=device-width, user-scalable=0", True),
    ("width=device-width, maximum-scale=1", True),
    ("width=device-width, maximum-scale=5", False),
])
def test_zoom_disabled(viewport, flagged):
    html = page("", head=f'<title>T</title><meta name="viewport" content="{viewport}">')
    assert ("zoom-disabled" in rules(html)) is flagged


def test_headings():
    no_h1 = '<!DOCTYPE html><html lang="en"><head><title>T</title></head><body><h2>Only h2</h2></body></html>'
    assert "page-has-h1" in rules(no_h1)
    assert rules(page("<h2>A</h2><h4>Skipped h3</h4>")) == ["heading-order"]
    assert rules(page("<h2>A</h2><h3>B</h3><h2>Back up is fine</h2>")) == []


def test_score_weights_by_severity():
    issues = audit_html(page('<img src="a.png"><a href="/x"></a><h3>skip</h3>'))
    assert sorted(i.rule for i in issues) == ["heading-order", "image-alt", "link-name"]
    assert page_score(issues) == 100 - 10 - 5 - 2


def test_every_rule_explains_why_and_how_to_fix():
    for rule in RULES.values():
        assert rule.severity in ("critical", "serious", "moderate")
        assert rule.why and rule.fix and rule.wcag
