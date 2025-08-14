# Chat Interfaces

These modules will be used to talk to the various chat interfaces.

They will involve class methods where you create an instance of the class,
it'll go connect to the channels based on the keys and config described,
it'll listen for messages from the various channels and it'll output the
messages from the users in the channels from the various apps installed.

Registers input/output methods in order to allow two-way communications
with the channels or DM's associated with the chat interface.

Takes some of the API edge off from talking with the chat apps.

## Chat Interface

Interface model to provide a consistent contract all of the contained models
will follow in order to enable a unified means of interfacing with the various
applications.

## Discord

Adapter model to connect to Discord as an "app" and interface with users.

## Slack

Adapter model to connect to Slack as an "app" and interface with users.

## MS Teams

Adapter model to connect to Microsoft Teams as an "app" and interface with users.
