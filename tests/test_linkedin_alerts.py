from src.ingest.base import SearchProfile
from src.ingest.linkedin import (
    LinkedInAlertsSource,
    parse_linkedin_alert,
)
from src.monitor.inbox import InboxMessage

# A trimmed-down but realistic LinkedIn alert body (two jobs + a logo anchor).
ALERT_HTML = """
<table>
  <tr><td>
    <a href="https://www.linkedin.com/comm/jobs/view/3812345678/?trk=eml-x">
      <img src="logo.png"/></a>
    <a href="https://www.linkedin.com/comm/jobs/view/3812345678/?trk=eml-jobtitle">
      Senior Backend Engineer</a>
    <span>Acme Pay &middot; S&atilde;o Paulo, Brazil &middot; Actively recruiting</span>
  </td></tr>
  <tr><td>
    <a href="https://www.linkedin.com/comm/jobs/view/3899999999/?trk=eml-jobtitle">
      Staff Python Engineer</a>
    <span>Globex &middot; Remote (Brazil) &middot; Be an early applicant</span>
  </td></tr>
</table>
"""


def test_parse_extracts_title_company_location_and_canonical_url():
    postings = parse_linkedin_alert("10 new jobs for 'engineer'", ALERT_HTML)
    assert len(postings) == 2                       # logo anchor collapsed into job 1
    p = {x.raw["job_id"]: x for x in postings}
    p1 = p["3812345678"]
    assert p1.title == "Senior Backend Engineer"
    assert p1.company == "Acme Pay"
    assert p1.location == "São Paulo, Brazil"        # noise ("Actively recruiting") trimmed
    assert p1.source == "linkedin"
    assert p1.source_url == "https://www.linkedin.com/jobs/view/3812345678"  # query stripped
    assert p["3899999999"].company == "Globex"


def _inbox(*msgs):
    class _Fake:
        def fetch(self):
            return list(msgs)
    return _Fake()


def test_source_ingests_only_linkedin_alerts_and_filters():
    alert = InboxMessage(subject="Jobs for you", body=ALERT_HTML,
                         from_addr="jobalerts-noreply@linkedin.com")
    spam = InboxMessage(subject="Buy now", body=ALERT_HTML, from_addr="ads@spam.com")
    src = LinkedInAlertsSource(_inbox(alert, spam))
    got = list(src.fetch(SearchProfile(keywords=["python"], recency_days=0)))
    # only the Python role matches the profile keyword; spam message is ignored
    assert len(got) == 1
    assert got[0].title == "Staff Python Engineer"


def test_source_dedupes_repeated_job_across_messages():
    a1 = InboxMessage(subject="Jobs", body=ALERT_HTML, from_addr="jobalerts-noreply@linkedin.com")
    a2 = InboxMessage(subject="Jobs again", body=ALERT_HTML, from_addr="jobs-listings@linkedin.com")
    src = LinkedInAlertsSource(_inbox(a1, a2))
    got = list(src.fetch(SearchProfile(recency_days=0)))
    assert len(got) == 2                             # 2 unique jobs, not 4


def test_non_alert_linkedin_by_subject_heuristic():
    # a LinkedIn sender not in the known list, but subject looks like a job alert
    msg = InboxMessage(subject="New jobs matching your search", body=ALERT_HTML,
                       from_addr="notifications@linkedin.com")
    src = LinkedInAlertsSource(_inbox(msg))
    assert len(list(src.fetch(SearchProfile(recency_days=0)))) == 2
