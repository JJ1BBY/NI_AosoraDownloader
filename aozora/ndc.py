"""NDC（日本十進分類法）の分類体系定義とコード解析ユーティリティ。"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class NdcNode:
    code: str               # マッチ用プレフィックス ("9", "91", "913", "K9" など)
    label: str              # 表示名
    children: list[NdcNode] = field(default_factory=list)


NDC_TREE: list[NdcNode] = [
    NdcNode("0", "0類 総記", [
        NdcNode("01", "01 図書館"),
        NdcNode("02", "02 図書・書誌"),
        NdcNode("07", "07 ジャーナリズム・新聞"),
        NdcNode("08", "08 叢書・全集"),
    ]),
    NdcNode("1", "1類 哲学・宗教", [
        NdcNode("10", "10 哲学"),
        NdcNode("12", "12 東洋思想"),
        NdcNode("13", "13 西洋哲学"),
        NdcNode("14", "14 心理学"),
        NdcNode("15", "15 倫理学・道徳"),
        NdcNode("16", "16 宗教"),
        NdcNode("17", "17 神道"),
        NdcNode("18", "18 仏教"),
        NdcNode("19", "19 キリスト教"),
    ]),
    NdcNode("2", "2類 歴史・地理", [
        NdcNode("21", "21 日本史"),
        NdcNode("22", "22 アジア・東洋史"),
        NdcNode("23", "23 ヨーロッパ史"),
        NdcNode("25", "25 北アメリカ史"),
        NdcNode("28", "28 伝記"),
        NdcNode("29", "29 地理・地誌・紀行"),
    ]),
    NdcNode("3", "3類 社会科学", [
        NdcNode("31", "31 政治"),
        NdcNode("32", "32 法律"),
        NdcNode("33", "33 経済"),
        NdcNode("36", "36 社会・社会問題"),
        NdcNode("37", "37 教育"),
        NdcNode("38", "38 民俗学・風俗習慣"),
        NdcNode("39", "39 国防・軍事"),
    ]),
    NdcNode("4", "4類 自然科学", [
        NdcNode("41", "41 数学"),
        NdcNode("42", "42 物理学"),
        NdcNode("43", "43 化学"),
        NdcNode("44", "44 天文学"),
        NdcNode("45", "45 地球科学・地学"),
        NdcNode("46", "46 生物科学"),
        NdcNode("47", "47 植物学"),
        NdcNode("48", "48 動物学"),
        NdcNode("49", "49 医学・薬学"),
    ]),
    NdcNode("5", "5類 技術・工学", [
        NdcNode("52", "52 建築学"),
        NdcNode("53", "53 機械工学"),
        NdcNode("54", "54 電気・電子工学"),
        NdcNode("55", "55 海洋・船舶工学"),
        NdcNode("57", "57 化学工業"),
        NdcNode("58", "58 製造工業"),
        NdcNode("59", "59 家政学・生活科学"),
    ]),
    NdcNode("6", "6類 産業", [
        NdcNode("61", "61 農業"),
        NdcNode("64", "64 畜産業・獣医学"),
        NdcNode("66", "66 水産業"),
        NdcNode("67", "67 商業・貿易"),
        NdcNode("68", "68 交通・運輸"),
    ]),
    NdcNode("7", "7類 芸術・美術", [
        NdcNode("71", "71 彫刻"),
        NdcNode("72", "72 絵画・書道"),
        NdcNode("73", "73 版画"),
        NdcNode("74", "74 写真・印刷"),
        NdcNode("75", "75 工芸"),
        NdcNode("76", "76 音楽・舞踊"),
        NdcNode("77", "77 演劇・映画"),
        NdcNode("78", "78 スポーツ・体育"),
        NdcNode("79", "79 諸芸・娯楽"),
    ]),
    NdcNode("8", "8類 言語", [
        NdcNode("81", "81 日本語"),
        NdcNode("82", "82 中国語"),
        NdcNode("83", "83 英語"),
        NdcNode("84", "84 ドイツ語"),
        NdcNode("85", "85 フランス語"),
        NdcNode("86", "86 スペイン語"),
        NdcNode("87", "87 イタリア語"),
        NdcNode("88", "88 ロシア語"),
        NdcNode("89", "89 その他の言語"),
    ]),
    NdcNode("9", "9類 文学", [
        NdcNode("91", "91 日本文学", [
            NdcNode("910", "910 日本文学（一般）"),
            NdcNode("911", "911 詩歌・俳諧"),
            NdcNode("912", "912 戯曲・脚本"),
            NdcNode("913", "913 小説・物語"),
            NdcNode("914", "914 評論・エッセイ・随筆"),
            NdcNode("915", "915 日記・書簡"),
            NdcNode("916", "916 記録・手記"),
            NdcNode("919", "919 漢文学"),
        ]),
        NdcNode("92", "92 中国文学"),
        NdcNode("93", "93 英米文学"),
        NdcNode("94", "94 ドイツ語文学"),
        NdcNode("95", "95 フランス語文学"),
        NdcNode("96", "96 スペイン語文学"),
        NdcNode("97", "97 イタリア語文学"),
        NdcNode("98", "98 ロシア語文学"),
        NdcNode("99", "99 その他の文学"),
    ]),
    NdcNode("K", "K類 児童書", [
        NdcNode("K2", "K2 歴史・地理"),
        NdcNode("K3", "K3 社会科学"),
        NdcNode("K4", "K4 自然科学"),
        NdcNode("K7", "K7 芸術・美術"),
        NdcNode("K9", "K9 文学"),
    ]),
]


def parse_ndc_codes(classification: str) -> list[str]:
    """'NDC 913 914' → ['913', '914']、'NDC K913' → ['K913']"""
    if not classification:
        return []
    s = classification.strip()
    if s == "NDC":
        return []
    if s.startswith("NDC "):
        s = s[4:].strip()
    return [p for p in s.split() if p]
