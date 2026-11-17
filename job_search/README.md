# Daily .NET/Azure Job Assistant

Uses Tharun's real profile to rank public-company ATS jobs and generate fresh LinkedIn 24-hour search links for Hyderabad and Remote.

Target roles include .NET, C#, ASP.NET Core, Azure backend and Software Engineer roles.

The profile does not claim Docker, Kubernetes, or hands-on Redis.

## LinkedIn

This repository intentionally does not log into LinkedIn, scrape LinkedIn pages, automate LinkedIn clicks, or auto-submit LinkedIn applications. LinkedIn's User Agreement prohibits unauthorized bots/automated access and scraping. The assistant therefore creates fresh 24-hour LinkedIn search links and public ATS application links for review.

## Daily output

- out/matched_jobs.csv
- out/daily_report.md

The workflow runs around 09:00 IST daily.

## Optional variables

GREENHOUSE = space-separated Greenhouse board slugs
LEVER = space-separated Lever company slugs
MIN_SCORE = minimum match score, default 60

The existing cold-email agent in this repository is preserved.
