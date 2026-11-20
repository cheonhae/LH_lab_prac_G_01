"""민원대장·홍보 예산 집계 스크립트 (M2판)

규칙: rules/aggregation_rules.md
실행(레포 최상위에서):
    python scripts/aggregate.py
    python scripts/aggregate.py --complaints inputs/m4/G-M4-02_민원대장_week2.csv --budget none --outdir outputs/m4
원본 CSV는 읽기만 한다. 결과는 --outdir 아래 summary.csv, excluded_rows.csv, run_log.md.
Python 표준 라이브러리만 쓴다.
"""
import argparse
import csv
import os
from decimal import Decimal, ROUND_HALF_UP

TYPES = ["자격·소득", "접수 기간·방법", "제출 서류", "임대 조건", "기타"]
METHODS = ["콜센터", "온라인", "방문"]
STATUSES = ["접수", "처리중", "답변완료"]
UNRESOLVED = ["접수", "처리중"]
# 신청방법 비표준 표기 대응표(rules/aggregation_rules.md 2.3)
METHOD_MAP = {"홈페이지": "온라인", "전화": "콜센터", "내방": "방문"}
# True면 대응표에도 없는 신청방법 표기를 '신청방법 확인 필요'로 제외한다
STRICT_METHOD = False
NOTICE = "> [가상 자료] 이 자료의 기관·인물·지구·업체·수치·연락처는 모두 실습용 가상 정보입니다. 실제 사실이 아니며 실무에 사용할 수 없습니다."


def file_id(path):
    return os.path.basename(path).split("_")[0]


def read_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = [r for r in reader if r]
    return header, rows


def pct(num, den):
    if den == 0:
        return "계산 불가"
    value = Decimal(num) * Decimal(100) / Decimal(den)
    return str(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def aggregate_complaints(path, summary, excluded, log):
    header, rows = read_rows(path)
    col = {name: i for i, name in enumerate(header)}
    fid = file_id(path)
    seen = {}
    valid = []
    fixed = []
    for n, row in enumerate(rows, start=1):
        no = row[col["접수번호"]]
        if no in seen:
            excluded.append([f"{fid} {n}행", f"중복 — {seen[no]}행과 접수번호 같음({no})", ",".join(row)])
            continue
        seen[no] = n
        method = row[col["신청방법"]]
        if method not in METHODS:
            if method in METHOD_MAP:
                fixed.append(f"{fid} {n}행: 신청방법 정규화 '{method}' → '{METHOD_MAP[method]}'")
                row = list(row)
                row[col["신청방법"]] = METHOD_MAP[method]
            elif STRICT_METHOD:
                excluded.append([f"{fid} {n}행", f"신청방법 확인 필요 — '{method}'", ",".join(row)])
                continue
        valid.append(row)
    dup_count = len(rows) - len(seen)
    other_excluded = len(rows) - dup_count - len(valid)
    summary.append(["민원", "원본 행 수", str(len(rows)), "행"])
    summary.append(["민원", "제외 행 수(중복)", str(dup_count), "행"])
    if STRICT_METHOD:
        summary.append(["민원", "제외 행 수(신청방법 확인 필요)", str(other_excluded), "행"])
    if METHOD_MAP:
        summary.append(["민원", "수정 행 수(신청방법 정규화)", str(len(fixed)), "행"])
    summary.append(["민원", "유효 민원 수", str(len(valid)), "건"])
    for t in TYPES:
        summary.append(["민원유형", t, str(sum(1 for r in valid if r[col["민원유형"]] == t)), "건"])
    others = sorted({r[col["민원유형"]] for r in valid} - set(TYPES))
    for t in others:
        summary.append(["민원유형", t, str(sum(1 for r in valid if r[col["민원유형"]] == t)), "건"])
    methods = METHODS + sorted({r[col["신청방법"]] for r in valid} - set(METHODS))
    for m in methods:
        summary.append(["신청방법", m, str(sum(1 for r in valid if r[col["신청방법"]] == m)), "건"])
    for s in STATUSES:
        summary.append(["처리상태", s, str(sum(1 for r in valid if r[col["처리상태"]] == s)), "건"])
    summary.append(["처리상태", "미처리(접수·처리중)", str(sum(1 for r in valid if r[col["처리상태"]] in UNRESOLVED)), "건"])
    log.append(f"## 민원대장 — `{path}`")
    log.append("")
    log.append(f"- 원본 데이터 행 수: {len(rows)}행 → 유효 민원 {len(valid)}건")
    log.append(f"- 제외: 중복 {dup_count}행" + (f", 신청방법 확인 필요 {other_excluded}행" if STRICT_METHOD else ""))
    log.append(f"- 수정 행: {len(fixed)}행")
    for line in fixed:
        log.append(f"  - {line}")
    log.append("")


def aggregate_budget(path, summary, excluded, log):
    header, rows = read_rows(path)
    col = {name: i for i, name in enumerate(header)}
    fid = file_id(path)
    included = []
    fixed = []
    corr_budget = 0
    corr_exec = 0
    n_total = n_corr = n_unit = n_bal = 0
    for n, row in enumerate(rows, start=1):
        if row[0] == "합계":
            excluded.append([f"{fid} {n}행", "합계 행", ",".join(row)])
            n_total += 1
            continue
        budget = int(row[col["예산"]])
        spent = int(row[col["집행"]])
        balance = int(row[col["잔액"]])
        if row[col["단위"]] == "천원":
            budget, spent, balance = budget * 1000, spent * 1000, balance * 1000
            fixed.append(f"{fid} {n}행: 단위 환산 천원 → 원(×1,000)")
            n_unit += 1
        if spent < 0:
            excluded.append([f"{fid} {n}행", "정정 — 담당 확인(집행 음수)", ",".join(row)])
            corr_budget += budget
            corr_exec += spent
            n_corr += 1
            continue
        if balance != budget - spent:
            fixed.append(f"{fid} {n}행: 잔액 재계산 {balance} → {budget - spent}")
            balance = budget - spent
            n_bal += 1
        included.append((budget, spent, balance))
    b_sum = sum(r[0] for r in included)
    e_sum = sum(r[1] for r in included)
    r_sum = sum(r[2] for r in included)
    summary.append(["예산", "원본 행 수", str(len(rows)), "행"])
    summary.append(["예산", "제외 행 수(합계 행)", str(n_total), "행"])
    summary.append(["예산", "제외 행 수(정정 — 담당 확인)", str(n_corr), "행"])
    summary.append(["예산", "수정 행 수(단위 환산)", str(n_unit), "행"])
    summary.append(["예산", "수정 행 수(잔액 재계산)", str(n_bal), "행"])
    summary.append(["예산", "집계 포함 행 수", str(len(included)), "행"])
    summary.append(["예산", "예산 합계", str(b_sum), "원"])
    summary.append(["예산", "집행 합계", str(e_sum), "원"])
    summary.append(["예산", "잔액 합계", str(r_sum), "원"])
    summary.append(["예산", "집행률", pct(e_sum, b_sum), "%"])
    summary.append(["예산", "정정 반영 참고 집행 합계", str(e_sum + corr_exec), "원"])
    summary.append(["예산", "정정 반영 참고 집행률", pct(e_sum + corr_exec, b_sum + corr_budget), "%"])
    log.append(f"## 홍보 예산 — `{path}`")
    log.append("")
    log.append(f"- 원본 데이터 행 수: {len(rows)}행 → 집계 포함 {len(included)}행")
    log.append(f"- 제외: 합계 행 {n_total}행, 정정 — 담당 확인 {n_corr}행")
    log.append(f"- 수정 행: {len(fixed)}행(단위 환산 {n_unit}, 잔액 재계산 {n_bal})")
    for line in fixed:
        log.append(f"  - {line}")
    log.append("")


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(header)
        w.writerows(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--complaints", default="inputs/m2/G-M2-01_민원대장_week1.csv")
    p.add_argument("--budget", default="inputs/m2/G-M2-02_홍보예산_집행현황.csv")
    p.add_argument("--outdir", default="outputs/m2")
    a = p.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    summary, excluded = [], []
    cmd = "python scripts/aggregate.py"
    if a.complaints != p.get_default("complaints") or a.budget != p.get_default("budget") or a.outdir != p.get_default("outdir"):
        cmd += f" --complaints {a.complaints} --budget {a.budget} --outdir {a.outdir}"
    log = [NOTICE, "", "# 실행 기록", "", f"- 실행 명령: `{cmd}`", "- 규칙: `rules/aggregation_rules.md`", ""]
    aggregate_complaints(a.complaints, summary, excluded, log)
    if a.budget != "none":
        aggregate_budget(a.budget, summary, excluded, log)
    log.append(f"- 결과: `{a.outdir}/summary.csv`({len(summary)}행), `{a.outdir}/excluded_rows.csv`({len(excluded)}행)")
    write_csv(os.path.join(a.outdir, "summary.csv"), ["구분", "항목", "값", "단위"], summary)
    write_csv(os.path.join(a.outdir, "excluded_rows.csv"), ["원본행", "사유", "원본값"], excluded)
    with open(os.path.join(a.outdir, "run_log.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(log) + "\n")
    for row in summary:
        print(",".join(row))


if __name__ == "__main__":
    main()
