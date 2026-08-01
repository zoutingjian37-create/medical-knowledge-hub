# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Existing local application: Python HTTP service with static HTML, CSS, and JavaScript pages. It is launched on Windows from a desktop shortcut and opens on localhost.

## Users

The primary user is an individual medical researcher building a personal Obsidian knowledge base. They collect public articles and videos, scan high-quality literature explanations, and turn useful material into research questions and feasible study plans.

## Product Purpose

Medical Knowledge Hub collects public content from WeChat, Zhihu, Bilibili, Xiaohongshu, and Douyin, and discovers medical literature from journal feeds and structured searches. It filters and deduplicates candidates, saves literature to Zotero, produces research-oriented summaries, and writes only user-approved results into Obsidian.

## Positioning

The product separates source discovery, platform parsing, knowledge distillation, human review, and Obsidian archiving. Its output is designed to support publishable medical research proposals, especially innovation discovery and current statistical methods, rather than merely copying articles into Markdown.

## Operating Context

The application runs locally on Windows. The user may paste a public link or manage daily subscriptions for WeChat accounts, journals, feeds, and literature queries. Code performs discovery, filtering, deduplication, Zotero import, and scheduling; Codex performs only the bounded knowledge-distillation step. Original article bodies are temporary, PDFs remain in Zotero, and the knowledge record keeps identifiers and source links.

## Capabilities and Constraints

- Manual public-link parsing is the dependable entry point for all five platforms.
- WeChat public-account discovery defaults to code-driven control of an already logged-in desktop WeChat session. Local OCR identifies the exact account, article rows, concrete publication dates, and the copy-link action; OpenCLI parses only the resulting public link.
- WeChat relative labels are normalized to Beijing calendar dates before filtering. The final discovery marker combines account, concrete publication date, and canonical public URL.
- The application must not request or expose WeChat Cookie, Token, chat databases, or other personal credentials.
- Non-WeChat platform reading can use OpenCLI, while collection, filtering, deduplication, review, and Obsidian archiving remain product-owned workflow stages.
- Saving to Obsidian is review-gated; parsing alone must not silently archive content.
- Daily automation defaults to off, 08:30, and at most five distilled items. Manual runs remain available while automation is off.
- Personal subscriptions live outside Git and must be explicitly exported/imported for migration. A fresh clone contains no author-specific sources.
- Literature discovery reuses RSS/Atom and public bibliographic APIs instead of a general publisher scraper.
- School access uses a user-controlled browser login and the official Zotero Connector; credentials are never collected.
- Current routes, module names, and working API contracts should remain stable during visual redesigns.
- The current product is optimized for one local user. Broader multi-user distribution is an open decision.

## Brand Commitments

The product name is Medical Knowledge Hub, shown in Chinese as “医学知识工作台”. Interface copy should be concise, plain Chinese that states what each action does. The product should feel trustworthy and research-oriented without claiming medical authority or inventing evidence.

## Evidence on Hand

The repository contains working local routes, platform adapters, security boundaries, knowledge-job lifecycle tests, Windows packaging, and an Obsidian approval workflow. There are no customer testimonials, usage benchmarks, institutional endorsements, or clinical claims; future work must not fabricate them.

## Product Principles

- Research value over verbatim collection.
- Innovation discovery over basic statistical teaching.
- Public links and local processing over credential-based scraping.
- Human confirmation before permanent knowledge-base writes.
- Reuse proven platform engines while keeping the user workflow coherent and replaceable.

## Accessibility & Inclusion

The primary interface language is Simplified Chinese. Core actions must remain keyboard accessible, legible at common Windows scaling settings, and usable on narrow browser windows.
