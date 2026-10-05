"""
Integrations: plain API clients. No model, no tool descriptions, no prompts.

They are used two ways (design doc, "Repository structure"):
  - tools/ wraps them so the model can call them
  - later, dashboard panels call them directly, with no model involved
"""
