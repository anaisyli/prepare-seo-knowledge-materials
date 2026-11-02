#!/usr/bin/env python3
"""List every sentence in the mail that might hold reusable company knowledge.

The whole mailbox is too long to read word by word, but a summary of each email
drops most of what matters. This scans all of it, keeps sentences written by the
company, drops repeats, and leaves a list short enough to read in full.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from package_common import load_json_object, write_json_file


KNOWLEDGE_TERMS = re.compile(
    r"(?i)\b\d{2,3}\s?(gsm|g/m|d\b)|\d{1,3}\s?%\s?(cotton|polyester|nylon|viscose|linen|wool|recycled|spandex)"
    r"|fabric|fleece|sherpa|flannel|jacquard|tapestry|canvas|corduroy|denim|plush|lining|padding|quilt|yarn|woven|knit"
    r"|print|embroider|dye|wash|shrink|pilling|fastness|repellent|waterproof|fire.?retard|anti.?"
    r"|oeko|gots|\bgrs\b|bsci|sedex|intertek|\bsgs\b|amfori|\bazo\b|reach\b|certificat|audit|test report"
    r"|lab.?dip|strike.?off|swatch|sample|pp sample|size set|fitting|bulk|production|factory|capacity|machine|workshop"
    r"|\bmoq\b|lead.?time|odm|oem|we (can|could|are able|have|develop|produce|make|offer|provide|specialize|usually|normally|always)"
    r"|our (factory|company|fabric|design|team|workshop|standard|usual|regular|normal)"
    r"|面料|克重|成分|工艺|工厂|车间|产能|验厂|认证|证书|检测|报告|打样|色卡|批色|水洗|缩水|起球|色牢度|印花|提花|绗缝|绣花|复合|大货|我们(可以|能|有|一般|通常|公司|工厂)|公司"
)
SIGNATURE = re.compile(
    r"(?i)confidential|privileged|disclaimer|intended recipient|unsubscribe|@[\w-]+\.\w+|https?://|www\.|"
    r"\btel\b|\bfax\b|\bmobile\b|wechat|whatsapp|add(ress)?:|best regards|b\.?rgds|kind regards|sent from|"
    r"^\s*(from|to|cc|subject|date|发件|收件|抄送|主题|日期)\s*[:：*]"
)
# Progress chatter about one order. It mentions fabric and samples constantly and
# states nothing that holds beyond that order.
ORDER_CHATTER = re.compile(
    r"(?i)\b(pls|please|kindly|thanks|thank you|sorry|dear|hi\b|hello|received?|attached|attachment|"
    r"today|tomorrow|yesterday|next week|this week|last week|asap|urgent|tracking|courier|dhl|fedex|ups\b|"
    r"invoice|payment|deposit|shipped|shipping|delivery date|etd|eta|po\b|p\.o\.|order no|style no|"
    r"confirm|approve|approved|comments?|check|follow up|remind|waiting|let me know|will send|have sent|sent you|"
    r"will be ready|send you|see below|as below|noted|update)\b|"
    r"请|麻烦|谢谢|收到|已寄|寄出|快递|单号|今天|明天|昨天|下周|本周|尽快|催|附件|确认|批复|发货|出货|船期|付款|定金|订单号|你好|您好"
)
# Sentences that state what the company can do, usually does, or holds. These are
# read one by one; the rest of the list is mostly talk about a particular style.
STATEMENT = re.compile(
    r"(?i)\b(we|our company|our factory)\s+(can|could|are able|have|develop|produce|make|offer|provide|specialize|"
    r"usually|normally|always|often|generally|do not|don'?t|can'?t|cannot|only|never|use|are)\b"
    r"|\bour\s+(factory|company|fabric|fabrics|design|designs|team|workshop|standard|usual|regular|normal|product|"
    r"products|main|own|new|machine|machines|capacity|moq)\b"
    r"|\b(usually|normally|generally|always|standard|regular|minimum|maximum|at least|in general|as a rule)\b"
    r"|oeko|gots|\bgrs\b|bsci|sedex|intertek|\bsgs\b|amfori|\bazo\b|certificat|audit|test report|factory|capacity|"
    r"workers?|machines?|一般|通常|常规|默认|最少|起订|工厂|车间|产能|验厂|认证|证书|检测|"
    r"我们(可以|能|有|公司|工厂)|公司(可以|能|有|主要|专注)"
)
BASE64_LIKE = re.compile(r"[A-Za-z0-9+/=]{40,}")
MESSAGE_HEADING = re.compile(r"(?m)^#{2,4}\s*(?:邮件|message|mail)\s*\d+.*$", re.I)
SENTENCE_END = re.compile(r"(?<=[.!?。！？；;])\s+|\n+")
MIN_LENGTH = 24
MAX_LENGTH = 240
MAX_SENTENCES_PER_MAIL = 40


def message_blocks(text: str) -> list[tuple[str, str]]:
    headings = list(MESSAGE_HEADING.finditer(text))
    if not headings:
        return [("", text)]
    blocks = []
    for position, heading in enumerate(headings):
        end = headings[position + 1].start() if position + 1 < len(headings) else len(text)
        blocks.append((heading.group(0), text[heading.end() : end]))
    return blocks


def is_own_message(heading: str, body: str, sent_marker: str, own_domains: list[str]) -> bool:
    """Keep what the company wrote. Without a way to tell, keep the message."""
    if not heading and not own_domains:
        return True
    if sent_marker and heading.rstrip().endswith(sent_marker):
        return True
    sender = re.search(r"(?m)^\W*(from|发件人?)\W*[:：].*$", body[:600], re.I)
    if own_domains and sender:
        return any(domain in sender.group(0).lower() for domain in own_domains)
    return not sent_marker and not own_domains


def strip_quoted(body: str) -> str:
    """Cut the quoted thread below a reply; each message is listed on its own."""
    match = re.search(r"(?m)^\W*(-{2,}\s*original message|on .{5,80} wrote:|原始邮件|发件人[:：]|from:\s)", body[40:], re.I)
    return body[: match.start() + 40] if match else body


def candidate_sentences(body: str) -> list[str]:
    found = []
    for raw in SENTENCE_END.split(body):
        sentence = re.sub(r"\s+", " ", raw.strip(" >*-_#\t"))
        if not MIN_LENGTH <= len(sentence) <= MAX_LENGTH:
            continue
        if BASE64_LIKE.search(sentence) or SIGNATURE.search(sentence):
            continue
        if ORDER_CHATTER.search(sentence):
            continue
        if KNOWLEDGE_TERMS.search(sentence):
            found.append(sentence)
    return found


def normalized(sentence: str) -> str:
    return re.sub(r"[\W_]+", "", sentence).casefold()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List candidate sentences from all mail items.")
    parser.add_argument("inventory", help="inventory.json")
    parser.add_argument("--work", required=True, help="Working directory outside the package")
    parser.add_argument("--sent-marker", default="", help="Text ending the heading of a sent message")
    parser.add_argument("--own-domain", action="append", default=[], help="Company mail domain, repeatable")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    domains = [domain.lower() for domain in args.own_domain]
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    scanned = 0
    without_candidates = 0
    read_errors: list[str] = []

    for item in load_json_object(Path(args.inventory)).get("items", []):
        if not item.get("is_mail"):
            continue
        try:
            text = Path(item["source_ref"]).read_text(encoding="utf-8", errors="replace")
        except OSError:
            read_errors.append(item["item_id"])
            continue
        scanned += 1
        kept = 0
        for heading, body in message_blocks(text):
            if not is_own_message(heading, body, args.sent_marker, domains):
                continue
            for sentence in candidate_sentences(strip_quoted(body)):
                key = normalized(sentence)
                if key in seen or kept >= MAX_SENTENCES_PER_MAIL:
                    continue
                seen.add(key)
                kept += 1
                records.append(
                    {
                        "item_id": item["item_id"],
                        "date": item.get("display_name", "")[:10],
                        "locator": heading.strip("# ").strip(),
                        "tier": "statement" if STATEMENT.search(sentence) else "other",
                        "sentence": sentence,
                    }
                )
        without_candidates += kept == 0

    with (work / "mail-candidates.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    summary = {
        "mails_scanned": scanned,
        "candidate_sentences": len(records),
        "statement_sentences": sum(1 for record in records if record["tier"] == "statement"),
        "mails_without_candidates": without_candidates,
        "characters": sum(len(record["sentence"]) for record in records),
        "read_errors": read_errors,
    }
    write_json_file(work / "mail-candidates-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if read_errors else 0


if __name__ == "__main__":
    sys.exit(main())
