"""수치 대장(ledger/ledger.csv)과 연결 문서의 수치를 대조한다.

실행(레포 최상위에서):
    python scripts/consistency_check.py --mode draft --minutes-before {고치기 전 회의록}   # 초안(inputs/m3) + 고치기 전 회의록 5절
    python scripts/consistency_check.py --mode updated   # 갱신본(outputs/m3/doc_*.md) 대조
    python scripts/consistency_check.py --mode both --minutes-before {고치기 전 회의록} --report outputs/m3/consistency_report.md
    python scripts/consistency_check.py --set m4 --mode both --minutes-before {정정 메모 반영 전 회의록} --report outputs/m4/consistency_report.md
회의록은 5절을 그 자리에서 고치므로, 고치기 전 회의록은 main의 이전 버전(GitHub 파일 이력의 Raw)을 따로 저장해 지정한다.
마지막 줄은 '불일치 N건'. 문서는 읽기만 한다. Python 표준 라이브러리만 쓴다.
"""
import argparse
import csv
import re

NOTICE = "> [가상 자료] 이 자료의 기관·인물·지구·업체·수치·연락처는 모두 실습용 가상 정보입니다. 실제 사실이 아니며 실무에 사용할 수 없습니다."

DOCS = {
    "m3": {
    "draft": [
        ("G-M3-01", "inputs/m3/G-M3-01_자료제출요청_공문_초안.md", None),
        ("G-M3-02", "inputs/m3/G-M3-02_주간민원보고_초안.md", None),
        ("G-M3-04", "inputs/m3/G-M3-04_지침_신구대비표_초안.md", None),
        ("회의록 5절", "outputs/m1/minutes.md", "## 5."),
    ],
    "updated": [
        ("G-M3-01", "outputs/m3/doc_G-M3-01.md", None),
        ("G-M3-02", "outputs/m3/doc_G-M3-02.md", None),
        ("G-M3-04", "outputs/m3/doc_G-M3-04.md", None),
        ("회의록 5절", "outputs/m1/minutes.md", "## 5."),
    ],
    },
    "m4": {
        "draft": [("회의록 5절", "outputs/m4/minutes.md", "## 5.")],
        "updated": [("회의록 5절", "outputs/m4/minutes.md", "## 5.")],
    },
}

DATE = r"(?:(\d{4})\. )?(\d{1,2})\. (\d{1,2})\.(?:\([월화수목금토일]\))?"
RANGE = re.compile(DATE + r"\s*~\s*" + DATE)
ONE_DATE = re.compile(DATE)


def iso(m, offset=0):
    year = m.group(1 + offset) or "2026"
    return f"{int(year):04d}-{int(m.group(2 + offset)):02d}-{int(m.group(3 + offset)):02d}"


def load_ledger(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {r["항목ID"]: r for r in csv.DictReader(f)}


def scoped_lines(path, section):
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    if section is None:
        return list(enumerate(lines, start=1))
    out, inside = [], False
    for n, line in enumerate(lines, start=1):
        if line.startswith("## "):
            inside = line.startswith(section)
            continue
        if inside:
            out.append((n, line))
    return out


def checks(line):
    """(대장 ID, 문서 값, 항목 설명) 목록을 돌려준다."""
    found = []
    if "접수 기간" in line:
        ranges = list(RANGE.finditer(line))
        if ranges:
            m = ranges[-1]
            found.append(("G-L03", iso(m, 0), "접수 시작일"))
            found.append(("G-L04", iso(m, 3), "접수 마감일"))
    if "접수 마감" in line:
        m = ONE_DATE.search(line, line.index("접수 마감"))
        if m:
            found.append(("G-L04", iso(m), "접수 마감일"))
    m = re.search(r"(?:접수|유효) 민원 (\d+)건", line)
    if m:
        found.append(("G-L05", m.group(1), "유효 민원 건수"))
    m = re.search(r"자격·소득 (\d+)건", line)
    if m:
        found.append(("G-L06", m.group(1), "자격·소득 건수"))
    m = re.search(r"미처리 (\d+)건", line)
    if m:
        found.append(("G-L07", m.group(1), "미처리 건수"))
    if "제출 기한" in line:
        m = ONE_DATE.search(line, line.index("제출 기한"))
        if m:
            found.append(("G-L11", iso(m), "자료 제출 기한"))
    if "설명회" in line and re.search(r"\d{2}:\d{2}", line):
        m = ONE_DATE.search(line, line.index("설명회"))
        if m:
            found.append(("G-L12", iso(m), "입주 설명회 일자"))
    if "정정공고" in line and "게시" in line:
        m = ONE_DATE.search(line, line.index("정정공고"))
        if m:
            found.append(("G-L02", iso(m), "정정공고 게시일"))
    return found


def checks_m4(line, ledger):
    """M4 대장 항목(있을 때만): 줄의 마지막 날짜를 본다."""
    found = []
    for word, lid, label in (("FAQ", "G-L17", "FAQ 개정본 게시일"), ("상담 인력", "G-L18", "상담 인력 예산 회신 기한")):
        if word in line and lid in ledger:
            dates = list(ONE_DATE.finditer(line))
            if dates:
                found.append((lid, iso(dates[-1]), label))
    return found


def ledger_value(row):
    value = row["값"]
    return value.split(" ")[0] if re.match(r"\d{4}-\d{2}-\d{2}", value) else value


def run(docset, mode, ledger, ledger_path, minutes_before=None):
    out = [f"## 대조 대상 — {mode}", "", f"- 대장: `{ledger_path}`", ""]
    out.append("| 문서 | 줄 | 대장 항목 | 문서 값 | 대장 값 | 결과 |")
    out.append("|---|---|---|---|---|---|")
    total = mismatch = 0
    for name, path, section in DOCS[docset][mode]:
        if mode == "draft" and section and minutes_before:
            path = minutes_before
        for n, line in scoped_lines(path, section):
            for lid, value, label in checks(line) + checks_m4(line, ledger):
                expected = ledger_value(ledger[lid])
                ok = value == expected
                total += 1
                mismatch += 0 if ok else 1
                out.append(f"| {name} | {n} | {lid} {label} | {value} | {expected} | {'일치' if ok else '불일치'} |")
    out.append("")
    out.append(f"- {mode}: 대조 {total}곳, 불일치 {mismatch}건")
    out.append("")
    return out, mismatch


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--set", dest="docset", choices=["m3", "m4"], default="m3")
    p.add_argument("--mode", choices=["draft", "updated", "both"], default="updated")
    p.add_argument("--ledger", default="ledger/ledger.csv")
    p.add_argument("--report")
    p.add_argument("--minutes-before", help="draft 대조에 쓸 고치기 전 회의록 파일")
    p.add_argument("--minutes-before-label", help="보고서에 적을 고치기 전 회의록의 출처 설명")
    a = p.parse_args()
    ledger = load_ledger(a.ledger)
    modes = ["draft", "updated"] if a.mode == "both" else [a.mode]
    cmd = "python scripts/consistency_check.py" + (" --set m4" if a.docset == "m4" else "") + " --mode " + a.mode
    if a.minutes_before:
        cmd += " --minutes-before {고치기 전 회의록}"
    out = [NOTICE, "", "# 정합 검사 결과", "", f"- 실행 명령: `{cmd}`"]
    if a.minutes_before:
        out.append(f"- 고치기 전 회의록: {a.minutes_before_label or a.minutes_before}")
    out.append("")
    counts = []
    for mode in modes:
        lines, mismatch = run(a.docset, mode, ledger, a.ledger, a.minutes_before)
        out.extend(lines)
        counts.append(mismatch)
    if len(counts) == 2:
        out.append(f"- 정정 반영 전(초안) 불일치 {counts[0]}건 → 갱신 후 {counts[1]}건")
    out.append(f"불일치 {counts[-1]}건")
    text = "\n".join(out) + "\n"
    if a.report:
        with open(a.report, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    print(text, end="")


if __name__ == "__main__":
    main()
