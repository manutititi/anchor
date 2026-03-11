# Anchor — Claude Code Project Config

## Refactor Session Workflow

Every chat session working on this refactor must follow these steps:

1. **Start** by reading `project.json` to load the current state of the project.
2. **Pick** a priority item from `refactor_priorities` (work high → medium → low).
3. **Work** on the selected item.
4. **When done**, append an entry to `refactor_log` inside `project.json`:
   ```json
   { "date": "YYYY-MM-DD", "session": "N", "change": "description", "files_touched": ["path/to/file"] }
   ```
5. **Update** `refactor_priorities` to mark completed items (remove or annotate as done).
