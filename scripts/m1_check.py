"""outputs/m1/evidence.md 각 행의 '값'에 든 숫자가 '위치'의 원문에 글자 그대로 있는지 찾는다.

- 표준 라이브러리만 쓴다. 파일은 읽기만 하고 아무것도 고치지 않는다.
- 뜻은 판단하지 않는다. 글자가 그대로 있는지만 본다.
- 위치에 발언 순번 [NN]이 있으면 전사본의 그 발언에서, 없으면 출처 파일 전체에서 찾는다.
  출처 파일과 위치가 ' / '로 여러 개면 같은 순서끼리 짝지어 각각 찾은 범위를 합친다.
- 값에 숫자가 없으면 '직접 확인'.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "outputs" / "m1" / "evidence.md"
INPUTS = ROOT / "inputs" / "m1"

# 날짜 → 시각 → 숫자(+%·단위) 순으로 앞에서부터 잘라 낸다.
TOKEN = re.compile(
    r"(?:\d{4}\. )?\d{1,2}\. \d{1,2}\.(?:\([월화수목금토일]\))?"  # 날짜: 2026. 11. 2.(월) / 11. 3.(화) / 10. 27.
    r"|\d{1,2}:\d{2}"                                               # 시각: 15:00
    r"|\d+(?:[.\-]\d+)*(?:%|[가-힣])?"                              # 건수·%·기타: 50건, 80석, 12.5%, 2026-41호
)
UTTER = re.compile(r"^\*\*\[(\d{2})\] [^:*]+:\*\*\s*(.*)$")
NUM_REF = re.compile(r"\[(\d{2})\]")


def read(path):
    return path.read_text(encoding="utf-8-sig")


def utterances(path):
    out = {}
    for line in read(path).splitlines():
        m = UTTER.match(line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def evidence_rows():
    rows = []
    for line in read(EVIDENCE).splitlines():
        if not re.match(r"^\| \d+ \|", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
        if len(cells) != 6:
            print(f"[경고] 칸 수가 6이 아닌 행: {line[:60]}", file=sys.stderr)
            continue
        rows.append(dict(zip(["no", "sentence", "value", "files", "loc", "status"], cells)))
    return rows


def search_text(row):
    """위치·출처 파일을 짝지어 찾을 원문을 모은다. (원문 목록, 설명)"""
    files = [f.strip() for f in row["files"].split(" / ")]
    locs = [l.strip() for l in row["loc"].split(" / ")]
    if len(locs) != len(files):          # 짝이 안 맞으면 위치 전체를 모든 파일에 적용
        locs = [row["loc"]] * len(files)
    texts, scope = [], []
    for f, loc in zip(files, locs):
        path = INPUTS / f
        if not path.exists():
            scope.append(f"{f}: 파일 없음")
            continue
        refs = NUM_REF.findall(loc)
        if refs:
            u = utterances(path)
            for r in refs:
                if r in u:
                    texts.append(u[r])
                    scope.append(f"[{r}]")
                else:
                    scope.append(f"[{r}] 없음")
        else:
            texts.append(read(path))
            scope.append(f"{f} 전체")
    return texts, ", ".join(scope)


def main():
    print("| # | 위치 | 값 | 결과(있음/없음/직접 확인) | 못 찾은 글자 |")
    print("|---|---|---|---|---|")
    counts = {"있음": 0, "없음": 0, "직접 확인": 0}
    for row in evidence_rows():
        tokens = TOKEN.findall(row["value"])
        if not tokens:
            result, missing = "직접 확인", "—"
        else:
            texts, _ = search_text(row)
            miss = [t for t in dict.fromkeys(tokens) if not any(t in x for x in texts)]
            result = "없음" if miss else "있음"
            missing = ", ".join(f"`{t}`" for t in miss) if miss else "—"
        counts[result] += 1
        print(f"| {row['no']} | {row['loc']} | {row['value']} | {result} | {missing} |")
    print()
    print("집계: " + " · ".join(f"{k} {v}" for k, v in counts.items()))
    print()
    print("찾은 범위")
    for row in evidence_rows():
        print(f"- #{row['no']}: {search_text(row)[1]}")


if __name__ == "__main__":
    main()
