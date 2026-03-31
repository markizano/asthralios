# Asthralios: Markizano's Assistant

In the [story of Markizano Draconus](https://story.markizano.net/), he creates an AI
that he uses to help him that becomes his main helping hand.

This is my attempt to re-create some semblance of this. This project has interfaces
to connect to various chat interfaces and perform a multitude of functions.
Just need to plan and implement all of this out.

## Features

### Sentinel: Code Quality Checker

Iterate over the code in the codebase (default working directory by default) and pass them in
front of an LLM to generate a confidence score around code policies are set.

### Ears: PA Whisper Stream

Run `asthralios ears` to listen literally from the microphone. Leverages whisper to capture
audio input and stream that to produce subtitles in near real-time.

I really want to optimize this better and see if I can't develop a better sub-gen agent for
Pulse Audio systems.

### FastMCP (wishlist)

I really want to learn and get into MCP more. This is a placeholder for those features when
they are built out.

### Slack/Discord Adapter

Right now, if you run `asthralios chat`, it'll connect to Slack and Discord as adapters and
will pass the conversation to an LLM to prove the point that any input works well for this.

I want to do more with this, so will continue to build on what's present.

### 2nd Brain / "Second Brain" (wishlist/in-brainstorm)

Nate B Jones talks about this at least a few times and has put together a decent summary on
how we can build this. It's not software. It's an idea! Put together whatever pieces to the
puzzle you want.

I'm thinking thru the implementation here since I don't like the services, prefer local-first
for something like this and really want to explore some of the more technical concepts like
a RAG pipeline, MCP and unstructured data classification.
