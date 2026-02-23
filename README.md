# Earnings Call Candor Analyzer

A Claude Code skill that grades earnings call transcripts on executive communication quality using L.J. Rittenhouse's *Investing Between the Lines* framework.

Given a full transcript, it produces a structured report scoring five dimensions: financial candor, strategic clarity, stakeholder balance, linguistic FOG, and long-term vision. Each dimension gets a letter grade with specific transcript evidence. The output is designed to help investors distinguish trustworthy disclosure from corporate obfuscation.

## Installation

### As a Claude Code skill

Add the skill to your Claude Code configuration by including the path to `SKILL.md` in your `~/.claude/settings.json`:

```json
{
  "skills": [
    "/path/to/earnings-call-analyzer/SKILL.md"
  ]
}
```

Or symlink it into your skills directory:

```bash
ln -s /path/to/earnings-call-analyzer/SKILL.md ~/.claude/skills/analyze-conference-call/SKILL.md
```

### Usage

Invoke the skill from Claude Code with a path to a transcript file:

```
/analyze-conference-call ~/path/to/transcript.txt
```

Transcripts should be plain text with speaker names on their own line followed by their remarks. The skill ignores operator/moderator boilerplate automatically.

## Transcript library

The `transcripts/` directory organizes earnings call transcripts by ticker and year:

```
transcripts/
  spot/
    2025/
      q1.txt
      q2.txt
      q3.txt
      q4.txt
  goog/
    2025/
      q1.txt
      q2.txt
      q3.txt
      q4.txt
```

Add new companies by creating a directory with their ticker symbol. Transcripts are plain `.txt` files sourced from earnings call webcasts or services like Seeking Alpha, The Motley Fool, or company investor relations pages.

## What it grades

| Dimension | Weight | What it measures |
|---|---|---|
| Capital Stewardship & Financial Candor | 25% | Specificity of financial disclosure, links to prior guidance, capital allocation rationale |
| Strategic Clarity & Accountability | 25% | Coherence of strategy, measurable milestones, consistency across periods |
| Stakeholder Balance & Culture Signals | 15% | Whether all stakeholders are addressed meaningfully, authenticity of voice |
| FOG Index | 20% | Clichés, weasel words, unsupported superlatives, Q&A evasion |
| Vision, Leadership & Long-Term Orientation | 15% | Falsifiable vision, problem disclosure, investor education, dualistic thinking |

Grades are composited into a weighted score (A through F) with full arithmetic shown.

## Background

Based on L.J. Rittenhouse's *Investing Between the Lines: How to Make Smarter Decisions by Decoding CEO Communications*. The core thesis: executive language quality predicts company performance. Candor builds trust; FOG (Fact-deficient, Obfuscating Generalities) destroys it.
