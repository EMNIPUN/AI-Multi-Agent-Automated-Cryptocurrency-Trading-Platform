# CryptoNova 3 — Page templates

All templates accept `title`, `description`, `modes`, `actions`, optional `toolbar`, and `children`. They render one page heading. The topbar keeps the breadcrumb only.

## Overview

Header, optional toolbar, then KPI and detail panels supplied by the page. Used when the job is status and summary: dashboard, portfolio, risk, system health.

## Trading terminal

Same header, with symbol, market, and timeframe controls passed as `toolbar` or as the first child. Markets uses the header actions for the connection badge. Positions keeps the existing read-only positions panel. There is no order-entry control.

## AI workspace

Fill-height frame for Orchestrator. The conversation scrolls inside the chat component. Below the `xl` breakpoint the right-hand context rail opens in a sheet labeled Context. Agent, live analysis, and LLM pages use the same header contract with their existing bodies.

## Operations

Autonomy and paper trading. Controls render only the commands the current supervisor state allows (`start`, `pause`, `resume`, `stop`, `halt`). Paper copy stays labeled simulated.

## Research

News, strategy, backtesting, and analytics. Backtesting no longer uses a separate oversized hero; the template heading is the only title. Fixture versus historical labeling stays in the existing backtest badges and notes.

## Settings

Settings, exchange connections, and notifications. Forms and read-only status stay in the page body. Credentials are not rendered.
