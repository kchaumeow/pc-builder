"""Builder: a build from chosen parts, and picking the next part for it."""

from collections.abc import Sequence
from dataclasses import dataclass

from pcbuilder.api.schemas import CategoryKey
from pcbuilder.api.views import CATEGORY_LABELS
from pcbuilder.catalog import Catalog
from pcbuilder.domain.compatibility import Issue, Severity, check
from pcbuilder.domain.models import Build, Component, ComponentType
from pcbuilder.recommender.solver import FILL_ORDER, needs, with_part

KEY_TO_CATEGORY = {
    CategoryKey(key): category for category, (key, _) in CATEGORY_LABELS.items()
}


class UnknownPart(LookupError):
    pass


def build_from_ids(catalog: Catalog, part_ids: Sequence[str]) -> Build:
    """A build from part ids. A part of the same category replaces the previous one;
    storage drives are added."""
    build = Build()
    for part_id in part_ids:
        try:
            part = catalog.get(part_id)
            catalog.price(part)  # a part without a price can't be bought
        except KeyError:
            raise UnknownPart(part_id) from None
        build = with_part(build, part)
    return build


def missing(build: Build) -> list[CategoryKey]:
    """Which parts are missing. The GPU isn't listed: it's optional if the CPU has
    integrated graphics, which check(complete=True) verifies."""
    return [
        CategoryKey(CATEGORY_LABELS[category][0])
        for category in FILL_ORDER
        if needs(build, category)
    ]


@dataclass
class Candidate:
    part: Component
    problems: list[Issue]  # new issues this part would introduce

    @property
    def compatible(self) -> bool:
        return all(issue.severity != Severity.ERROR for issue in self.problems)


@dataclass
class SearchResult:
    matched: int
    compatible: int
    candidates: list[Candidate]


def _issue_key(issue: Issue) -> tuple[str, str]:
    return issue.rule, issue.message


def search(
    catalog: Catalog,
    build: Build,
    category: ComponentType,
    query: str = "",
    include_incompatible: bool = False,
    limit: int = 30,
) -> SearchResult:
    """Parts of a category matching the query, cheapest first, compatible ones first.

    Each part is checked as part of the build: in place of the current one (or, for
    storage, in addition). Issues the build already had are not attributed to the part.
    """
    words = query.lower().split()
    already = {_issue_key(issue) for issue in check(build)}

    compatible: list[Candidate] = []
    incompatible: list[Candidate] = []
    matched = 0
    for part in catalog.candidates(category):
        name = part.name.lower()
        if not all(word in name for word in words):
            continue
        matched += 1
        problems = [
            issue
            for issue in check(with_part(build, part))
            if _issue_key(issue) not in already
        ]
        candidate = Candidate(part, problems)
        (compatible if candidate.compatible else incompatible).append(candidate)

    shown = compatible + incompatible if include_incompatible else compatible
    return SearchResult(matched, len(compatible), shown[:limit])
