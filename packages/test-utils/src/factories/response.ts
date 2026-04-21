import { Factory } from 'fishery';

export interface JsonApiError {
  status?: string;
  code?: string;
  title?: string;
  detail?: string;
  source?: {
    pointer?: string;
    parameter?: string;
  };
  meta?: Record<string, unknown>;
}

export interface JsonApiResource<T = Record<string, unknown>> {
  type: string;
  id: string;
  attributes: T;
  relationships?: Record<string, unknown>;
  links?: Record<string, string>;
  meta?: Record<string, unknown>;
}

export interface JsonApiDocument<T = Record<string, unknown>> {
  data: JsonApiResource<T> | JsonApiResource<T>[] | null;
  jsonapi: { version: string };
  links?: Record<string, string | null>;
  meta?: Record<string, unknown>;
  included?: JsonApiResource[];
}

export interface JsonApiErrorDocument {
  errors: JsonApiError[];
  jsonapi?: { version: string };
  meta?: Record<string, unknown>;
}

export type ResponseTransientParams = {
  body?: unknown;
  status?: number;
  statusText?: string;
  contentType?: string;
  headers?: Record<string, string>;
  jsonApi?: boolean;
  jsonApiVersion?: string;
};

const STATUS_TEXT_MAP: Record<number, string> = {
  200: 'OK',
  201: 'Created',
  204: 'No Content',
  400: 'Bad Request',
  401: 'Unauthorized',
  403: 'Forbidden',
  404: 'Not Found',
  409: 'Conflict',
  422: 'Unprocessable Entity',
  429: 'Too Many Requests',
  500: 'Internal Server Error',
  502: 'Bad Gateway',
  503: 'Service Unavailable',
};

function getStatusText(status: number): string {
  return STATUS_TEXT_MAP[status] || 'Unknown';
}

function wrapJsonApi<T>(
  data: JsonApiResource<T> | JsonApiResource<T>[] | null,
  options: {
    version?: string;
    meta?: Record<string, unknown>;
    links?: Record<string, string | null>;
    included?: JsonApiResource[];
  } = {}
): JsonApiDocument<T> {
  return {
    data,
    jsonapi: { version: options.version || '1.1' },
    ...(options.links && { links: options.links }),
    ...(options.meta && { meta: options.meta }),
    ...(options.included && { included: options.included }),
  };
}

function createJsonApiError(
  status: number,
  detail: string,
  options: {
    code?: string;
    title?: string;
    source?: { pointer?: string; parameter?: string };
    meta?: Record<string, unknown>;
  } = {}
): JsonApiError {
  return {
    status: String(status),
    detail,
    ...(options.code && { code: options.code }),
    ...(options.title && { title: options.title }),
    ...(options.source && { source: options.source }),
    ...(options.meta && { meta: options.meta }),
  };
}

export const responseFactory = Factory.define<Response, ResponseTransientParams>(
  ({ transientParams }) => {
    const {
      body = { status: 'ok' },
      status = 200,
      statusText,
      contentType,
      headers = {},
      jsonApi = false,
    } = transientParams;

    const resolvedContentType =
      contentType || (jsonApi ? 'application/vnd.api+json' : 'application/json');

    const responseHeaders: Record<string, string> = {
      'Content-Type': resolvedContentType,
      ...headers,
    };

    const bodyString = body !== undefined ? JSON.stringify(body) : '';

    return new Response(bodyString, {
      status,
      statusText: statusText || getStatusText(status),
      headers: responseHeaders,
    });
  }
);

export const responseFactoryHelpers = {
  json<T>(body: T, status = 200, headers: Record<string, string> = {}): Response {
    return responseFactory.build({}, {
      transient: { body, status, headers }
    });
  },

  jsonApiSuccess<T>(
    resource: JsonApiResource<T> | JsonApiResource<T>[],
    options: {
      status?: number;
      meta?: Record<string, unknown>;
      links?: Record<string, string | null>;
      included?: JsonApiResource[];
    } = {}
  ): Response {
    const body = wrapJsonApi(resource, options);
    return responseFactory.build({}, {
      transient: {
        body,
        status: options.status || 200,
        jsonApi: true,
      }
    });
  },

  jsonApiCollection<T>(
    resources: JsonApiResource<T>[],
    options: {
      count?: number;
      links?: Record<string, string | null>;
      included?: JsonApiResource[];
    } = {}
  ): Response {
    const body = wrapJsonApi(resources, {
      meta: { count: options.count ?? resources.length },
      links: options.links || {},
      included: options.included,
    });
    return responseFactory.build({}, {
      transient: {
        body,
        status: 200,
        jsonApi: true,
      }
    });
  },

  jsonApiError(
    status: number,
    errors: JsonApiError | JsonApiError[],
    options: { meta?: Record<string, unknown> } = {}
  ): Response {
    const errorArray = Array.isArray(errors) ? errors : [errors];
    const body: JsonApiErrorDocument = {
      errors: errorArray,
      jsonapi: { version: '1.1' },
      ...(options.meta && { meta: options.meta }),
    };
    return responseFactory.build({}, {
      transient: {
        body,
        status,
        jsonApi: true,
      }
    });
  },

  notFound(detail = 'Resource not found'): Response {
    return this.jsonApiError(404, createJsonApiError(404, detail, {
      title: 'Not Found',
    }));
  },

  badRequest(detail: string, source?: { pointer?: string; parameter?: string }): Response {
    return this.jsonApiError(400, createJsonApiError(400, detail, {
      title: 'Bad Request',
      source,
    }));
  },

  unauthorized(detail = 'Authentication required'): Response {
    return this.jsonApiError(401, createJsonApiError(401, detail, {
      title: 'Unauthorized',
    }));
  },

  forbidden(detail = 'Access denied'): Response {
    return this.jsonApiError(403, createJsonApiError(403, detail, {
      title: 'Forbidden',
    }));
  },

  validationError(
    errors: Array<{ field: string; detail: string; code?: string }>
  ): Response {
    const jsonApiErrors = errors.map(err =>
      createJsonApiError(422, err.detail, {
        code: err.code,
        title: 'Validation Error',
        source: { pointer: `/data/attributes/${err.field}` },
      })
    );
    return this.jsonApiError(422, jsonApiErrors);
  },

  serverError(detail = 'Internal server error'): Response {
    return this.jsonApiError(500, createJsonApiError(500, detail, {
      title: 'Internal Server Error',
    }));
  },

  rateLimited(retryAfter: number | string): Response {
    return responseFactory.build({}, {
      transient: {
        body: '',
        status: 429,
        headers: {
          'Retry-After': String(retryAfter),
        },
      }
    });
  },

  empty(status = 204): Response {
    return new Response(null, {
      status,
      statusText: getStatusText(status),
    });
  },

  text(body: string, status = 200, contentType = 'text/plain'): Response {
    return new Response(body, {
      status,
      statusText: getStatusText(status),
      headers: { 'Content-Type': contentType },
    });
  },
};

export { wrapJsonApi, createJsonApiError, getStatusText };
