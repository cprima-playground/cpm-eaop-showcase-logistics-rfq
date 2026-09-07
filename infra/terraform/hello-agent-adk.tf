# spikes/hello-agent-adk, deployed via vertexai.agent_engines.create()
# (not Terraform originally). Config below generated from live state via
# `terraform plan -generate-config-out`, then reviewed - not hand-written.
# google_vertex_ai_reasoning_engine requires provider >= ~7.x; the config
# didn't exist until upgrading past this repo's initial 6.50.0 install.
resource "google_vertex_ai_reasoning_engine" "hello_agent_adk" {
  deletion_policy = "FORCE"
  description     = "Minimal hello-world ADK agent spike, deployed from cpm-eaop-showcase-logistics-rfq."
  display_name    = "hello_agent_adk (showcase-rfq spike)"
  labels          = {}
  project         = "cpm-geap-2026"
  region          = "us-central1"
  spec {
    agent_framework = "google-adk"
    class_methods = jsonencode([{
      api_mode    = ""
      description = "Deprecated. Use async_get_session instead.\n\nGet a session for the given user.\n"
      name        = "get_session"
      parameters = {
        properties = {
          session_id = {
            type = "string"
          }
          user_id = {
            type = "string"
          }
        }
        required = ["user_id", "session_id"]
        type     = "object"
      }
      }, {
      api_mode    = ""
      description = "Deprecated. Use async_list_sessions instead.\n\nList sessions for the given user.\n"
      name        = "list_sessions"
      parameters = {
        properties = {
          user_id = {
            type = "string"
          }
        }
        required = ["user_id"]
        type     = "object"
      }
      }, {
      api_mode    = ""
      description = "Deprecated. Use async_create_session instead.\n\nCreates a new session.\n"
      name        = "create_session"
      parameters = {
        properties = {
          session_id = {
            nullable = true
            type     = "string"
          }
          state = {
            nullable = true
            type     = "object"
          }
          user_id = {
            type = "string"
          }
        }
        required = ["user_id"]
        type     = "object"
      }
      }, {
      api_mode    = ""
      description = "Deprecated. Use async_delete_session instead.\n\nDeletes a session for the given user.\n"
      name        = "delete_session"
      parameters = {
        properties = {
          session_id = {
            type = "string"
          }
          user_id = {
            type = "string"
          }
        }
        required = ["user_id", "session_id"]
        type     = "object"
      }
      }, {
      api_mode    = "async"
      description = "Get a session for the given user.\n\nArgs:\n    user_id (str):\n        Required. The ID of the user.\n    session_id (str):\n        Required. The ID of the session.\n    **kwargs (dict[str, Any]):\n        Optional. Additional keyword arguments to pass to the\n        session service.\n\nReturns:\n    Session: The session instance (if any). It returns None if the\n    session is not found.\n\nRaises:\n    RuntimeError: If the session is not found.\n"
      name        = "async_get_session"
      parameters = {
        properties = {
          session_id = {
            type = "string"
          }
          user_id = {
            type = "string"
          }
        }
        required = ["user_id", "session_id"]
        type     = "object"
      }
      }, {
      api_mode    = "async"
      description = "List sessions for the given user.\n\nArgs:\n    user_id (str):\n        Required. The ID of the user.\n    **kwargs (dict[str, Any]):\n        Optional. Additional keyword arguments to pass to the\n        session service.\n\nReturns:\n    ListSessionsResponse: The list of sessions.\n"
      name        = "async_list_sessions"
      parameters = {
        properties = {
          user_id = {
            type = "string"
          }
        }
        required = ["user_id"]
        type     = "object"
      }
      }, {
      api_mode    = "async"
      description = "Creates a new session.\n\nArgs:\n    user_id (str):\n        Required. The ID of the user.\n    session_id (str):\n        Optional. The ID of the session. If not provided, an ID\n        will be be generated for the session.\n    state (dict[str, Any]):\n        Optional. The initial state of the session.\n    ttl (str):\n        Optional. The time-to-live for the session.\n    expire_time (str):\n        Optional. The expiration time for the session.\n    **kwargs (dict[str, Any]):\n        Optional. Additional keyword arguments to pass to the\n        session service.\n\nReturns:\n    Session: The newly created session instance.\n"
      name        = "async_create_session"
      parameters = {
        properties = {
          session_id = {
            nullable = true
            type     = "string"
          }
          state = {
            nullable = true
            type     = "object"
          }
          user_id = {
            type = "string"
          }
        }
        required = ["user_id"]
        type     = "object"
      }
      }, {
      api_mode    = "async"
      description = "Deletes a session for the given user.\n\nArgs:\n    user_id (str):\n        Required. The ID of the user.\n    session_id (str):\n        Required. The ID of the session.\n    **kwargs (dict[str, Any]):\n        Optional. Additional keyword arguments to pass to the\n        session service.\n"
      name        = "async_delete_session"
      parameters = {
        properties = {
          session_id = {
            type = "string"
          }
          user_id = {
            type = "string"
          }
        }
        required = ["user_id", "session_id"]
        type     = "object"
      }
      }, {
      api_mode    = "async"
      description = "Generates memories.\n\nArgs:\n    session (Dict[str, Any]):\n        Required. The session to use for generating memories. It should\n        be a dictionary representing an ADK Session object, e.g.\n        session.model_dump(mode=\"json\").\n"
      name        = "async_add_session_to_memory"
      parameters = {
        properties = {
          session = {
            additionalProperties = true
            type                 = "object"
          }
        }
        required = ["session"]
        type     = "object"
      }
      }, {
      api_mode    = "async"
      description = "Searches memories for the given user.\n\nArgs:\n    user_id: The id of the user.\n    query: The query to match the memories on.\n\nReturns:\n    A SearchMemoryResponse containing the matching memories.\n"
      name        = "async_search_memory"
      parameters = {
        properties = {
          query = {
            type = "string"
          }
          user_id = {
            type = "string"
          }
        }
        required = ["user_id", "query"]
        type     = "object"
      }
      }, {
      api_mode    = "stream"
      description = "Deprecated. Use async_stream_query instead.\n\nStreams responses from the ADK application in response to a message.\n\nArgs:\n    message (Union[str, Dict[str, Any]]):\n        Required. The message to stream responses for.\n    user_id (str):\n        Required. The ID of the user.\n    session_id (str):\n        Optional. The ID of the session. If not provided, a new\n        session will be created for the user.\n    run_config (Optional[Dict[str, Any]]):\n        Optional. The run config to use for the query. If you want to\n        pass in a `run_config` pydantic object, you can pass in a dict\n        representing it as `run_config.model_dump(mode=\"json\")`.\n    **kwargs (dict[str, Any]):\n        Optional. Additional keyword arguments to pass to the\n        runner.\n\nYields:\n    The output of querying the ADK application.\n"
      name        = "stream_query"
      parameters = {
        properties = {
          message = {
            anyOf = [{
              type = "string"
              }, {
              additionalProperties = true
              type                 = "object"
            }]
          }
          run_config = {
            nullable = true
            type     = "object"
          }
          session_id = {
            nullable = true
            type     = "string"
          }
          user_id = {
            type = "string"
          }
        }
        required = ["message", "user_id"]
        type     = "object"
      }
      }, {
      api_mode    = "async_stream"
      description = "Streams responses asynchronously from the ADK application.\n\nArgs:\n    message (str):\n        Required. The message to stream responses for.\n    user_id (str):\n        Required. The ID of the user.\n    session_id (str):\n        Optional. The ID of the session. If not provided, a new\n        session will be created for the user. If this is specified, then\n        `session_events` will be ignored.\n    session_events (Optional[List[Dict[str, Any]]]):\n        Optional. The session events to use for the query. This will be\n        used to initialize the session if `session_id` is not provided.\n    run_config (Optional[Dict[str, Any]]):\n        Optional. The run config to use for the query. If you want to\n        pass in a `run_config` pydantic object, you can pass in a dict\n        representing it as `run_config.model_dump(mode=\"json\")`.\n    **kwargs (dict[str, Any]):\n        Optional. Additional keyword arguments to pass to the\n        runner.\n\nYields:\n    Event dictionaries asynchronously.\n\nRaises:\n    TypeError: If message is not a string or a dictionary representing\n    a Content object.\n    ValueError: If both session_id and session_events are specified.\n"
      name        = "async_stream_query"
      parameters = {
        properties = {
          message = {
            anyOf = [{
              type = "string"
              }, {
              additionalProperties = true
              type                 = "object"
            }]
          }
          run_config = {
            nullable = true
            type     = "object"
          }
          session_events = {
            nullable = true
            type     = "array"
          }
          session_id = {
            nullable = true
            type     = "string"
          }
          user_id = {
            type = "string"
          }
        }
        required = ["message", "user_id"]
        type     = "object"
      }
      }, {
      api_mode    = "async_stream"
      description = "Streams responses asynchronously from the ADK application.\n\nIn general, you should use `async_stream_query` instead, as it has a\nmore structured API and works with the respective ADK services that\nyou have defined for the AdkApp. This method is primarily meant for\ninvocation from AgentSpace.\n\nArgs:\n    request_json (str):\n        Required. The request to stream responses for.\n"
      name        = "streaming_agent_run_with_events"
      parameters = {
        properties = {
          request_json = {
            type = "string"
          }
        }
        required = ["request_json"]
        type     = "object"
      }
    }])
    identity_type   = null
    service_account = null
    package_spec {
      dependency_files_gcs_uri = "gs://cpm-geap-2026-agent-engine-staging/agent_engine/dependencies.tar.gz"
      pickle_object_gcs_uri    = "gs://cpm-geap-2026-agent-engine-staging/agent_engine/agent_engine.pkl"
      python_version           = "3.14"
      requirements_gcs_uri     = "gs://cpm-geap-2026-agent-engine-staging/agent_engine/requirements.txt"
    }
  }
}
