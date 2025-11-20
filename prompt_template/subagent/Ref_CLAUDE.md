## Rules

- Before you do any work, MUST view files in .claude/tasks/context_session_x.md file to get the full context (x being the id of the session we are operate, if file doesn't exist, then create one)
- context_session_x.md should contain most of context of what we did, overall plan, and sub agents will continusly add context to the file
- After you finish the work, MUST update the .claude/tasks/context_session_x.md file to make sure others can get full context of what you did

### Sub agents
You have access to 2 sub agents:
- vercel-ai-sdk-v5-expert: all task related to vercel ai sdk HAVE TO consult this agent
- shadcn-ui-builder: all task related to UI building & tweaking HAVE TO consult this agent
Sub agents will do research about the implementation, but you will do the actual implementation;
When passing task to sub agent, make sure you pass the context file, e.g. '.claude/tasks/session_context_x.md',
After each sub agent finish the work, make sure you read the related documentation they created to get full context of the plan before you start executing
