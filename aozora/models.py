from dataclasses import dataclass, field


@dataclass
class Work:
    work_id: str
    title: str
    title_reading: str
    subtitle: str
    authors: list[str] = field(default_factory=list)
    translators: list[str] = field(default_factory=list)
    classification: str = ""
    charset_type: str = ""
    text_url: str = ""
    text_encoding: str = ""
    html_url: str = ""
    card_url: str = ""
    release_date: str = ""
    last_updated: str = ""
    copyright: str = ""
    ndc_codes: list[str] = field(default_factory=list, init=False)

    def __post_init__(self):
        from .ndc import parse_ndc_codes
        self.ndc_codes = parse_ndc_codes(self.classification)

    @property
    def authors_display(self) -> str:
        return "、".join(self.authors)

    @property
    def translators_display(self) -> str:
        return "、".join(self.translators)

    @property
    def has_text_file(self) -> bool:
        return bool(self.text_url)
