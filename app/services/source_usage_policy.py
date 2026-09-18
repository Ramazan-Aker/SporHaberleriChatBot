from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit


class SourceUsageStatus(StrEnum):
    RSS_LINK_ONLY = "rss_link_only"
    PERMISSION_REQUIRED = "permission_required"
    UNREVIEWED = "unreviewed"


@dataclass(frozen=True, slots=True)
class SourceUsagePolicy:
    status: SourceUsageStatus
    terms_url: str | None
    note: str


_POLICIES: dict[str, SourceUsagePolicy] = {
    "trthaber.com": SourceUsagePolicy(
        status=SourceUsageStatus.RSS_LINK_ONLY,
        terms_url="https://www.trthaber.com/sitene_ekle.html",
        note=(
            "Resmi RSS sunuluyor; yalnız kısa yeniden yazılmış özet, kaynak ve "
            "bağlantı kullanılmalı. Ticari yeniden yayın lisansı teyit edilmedi."
        ),
    ),
    "aspor.com.tr": SourceUsagePolicy(
        status=SourceUsageStatus.RSS_LINK_ONLY,
        terms_url="https://www.aspor.com.tr/rss-bilgi",
        note=(
            "Resmi RSS sunuluyor; yalnız kısa yeniden yazılmış özet, kaynak ve "
            "bağlantı kullanılmalı. Ticari yeniden yayın lisansı teyit edilmedi."
        ),
    ),
    "transfermarkt.com.tr": SourceUsagePolicy(
        status=SourceUsageStatus.PERMISSION_REQUIRED,
        terms_url="https://www.transfermarkt.com.tr/intern/anb",
        note="İçerik hakları saklı; ticari kullanım için yazılı izin gerekli.",
    ),
    "haberturk.com": SourceUsagePolicy(
        status=SourceUsageStatus.PERMISSION_REQUIRED,
        terms_url="https://www.haberturk.com/kullanim-kosullari",
        note="Haber ve materyal kullanımı açık yazılı izne bağlı.",
    ),
    "ntvspor.net": SourceUsagePolicy(
        status=SourceUsageStatus.PERMISSION_REQUIRED,
        terms_url="https://www.ntvspor.net/kullanim-kosullari",
        note="Haber ve materyal kullanımı açık yazılı izne bağlı.",
    ),
}


def _hostname(value: str) -> str:
    return (urlsplit(value).hostname or "").casefold().removeprefix("www.")


def _policy_for_url(value: str) -> SourceUsagePolicy | None:
    hostname = _hostname(value)
    for domain, policy in _POLICIES.items():
        if hostname == domain or hostname.endswith(f".{domain}"):
            return policy
    return None


def classify_source_usage(url: str, rss_url: str) -> SourceUsagePolicy:
    policies = [
        policy
        for value in (url, rss_url)
        if (policy := _policy_for_url(value)) is not None
    ]
    if not policies:
        return SourceUsagePolicy(
            status=SourceUsageStatus.UNREVIEWED,
            terms_url=None,
            note="Kaynak kullanım koşulları production öncesinde incelenmeli.",
        )
    if any(
        policy.status == SourceUsageStatus.PERMISSION_REQUIRED for policy in policies
    ):
        return next(
            policy
            for policy in policies
            if policy.status == SourceUsageStatus.PERMISSION_REQUIRED
        )
    return policies[0]


def source_requires_permission(url: str, rss_url: str) -> bool:
    return (
        classify_source_usage(url, rss_url).status
        == SourceUsageStatus.PERMISSION_REQUIRED
    )


def source_is_approved_for_use(url: str, rss_url: str) -> bool:
    return classify_source_usage(url, rss_url).status == SourceUsageStatus.RSS_LINK_ONLY
