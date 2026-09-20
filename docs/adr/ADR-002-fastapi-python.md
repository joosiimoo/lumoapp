# ADR-002: FastAPI and Python for the backend

- Status: Accepted
- Date: 2026-09-19

## Decision

The backend is a Python 3.12 FastAPI application. FastAPI hosts the HTTP gateway, composition root, and modular monolith packages. Domain code does not import FastAPI.
