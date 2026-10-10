#include <curl/curl.h>
#include <ctype.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>

typedef struct {
    char *data;
    size_t length;
} AxisBuffer;

typedef struct {
    long status;
    char *body;
    size_t body_length;
    char *link_header;
    char *error;
} AxisHttpResponse;

typedef struct {
    CURL *easy;
} AxisHttpClient;

int axis_http_init(void) {
    return curl_global_init(CURL_GLOBAL_DEFAULT) == CURLE_OK ? 0 : 1;
}

AxisHttpClient *axis_http_client_new(void) {
    AxisHttpClient *client = calloc(1, sizeof(*client));
    if (client == NULL) {
        return NULL;
    }
    client->easy = curl_easy_init();
    if (client->easy == NULL) {
        free(client);
        return NULL;
    }
    return client;
}

void axis_http_client_free(AxisHttpClient *client) {
    if (client == NULL) {
        return;
    }
    curl_easy_cleanup(client->easy);
    free(client);
}

static char *axis_copy_string(const char *value, size_t length) {
    char *copy = malloc(length + 1);
    if (copy == NULL) {
        return NULL;
    }
    memcpy(copy, value, length);
    copy[length] = '\0';
    return copy;
}

static size_t axis_write_body(char *data, size_t size, size_t count, void *user_data) {
    size_t incoming = size * count;
    AxisBuffer *buffer = user_data;
    char *grown = realloc(buffer->data, buffer->length + incoming + 1);
    if (grown == NULL) {
        return 0;
    }
    buffer->data = grown;
    memcpy(buffer->data + buffer->length, data, incoming);
    buffer->length += incoming;
    buffer->data[buffer->length] = '\0';
    return incoming;
}

static size_t axis_write_header(char *data, size_t size, size_t count, void *user_data) {
    size_t length = size * count;
    AxisHttpResponse *response = user_data;
    const char prefix[] = "Link:";
    if (length < sizeof(prefix) - 1 || strncasecmp(data, prefix, sizeof(prefix) - 1) != 0) {
        return length;
    }

    size_t start = sizeof(prefix) - 1;
    while (start < length && isspace((unsigned char)data[start])) {
        start++;
    }
    size_t end = length;
    while (end > start && isspace((unsigned char)data[end - 1])) {
        end--;
    }
    char *link = axis_copy_string(data + start, end - start);
    if (link == NULL) {
        return 0;
    }
    free(response->link_header);
    response->link_header = link;
    return length;
}

static struct curl_slist *axis_headers(const char *headers, char **error) {
    struct curl_slist *list = NULL;
    const char *line = headers;
    while (line != NULL && *line != '\0') {
        const char *end = strchr(line, '\n');
        size_t length = end == NULL ? strlen(line) : (size_t)(end - line);
        while (length > 0 && line[length - 1] == '\r') {
            length--;
        }
        if (length > 0) {
            char *header = axis_copy_string(line, length);
            if (header == NULL) {
                const char message[] = "Out of memory while preparing headers.";
                *error = axis_copy_string(message, sizeof(message) - 1);
                curl_slist_free_all(list);
                return NULL;
            }
            struct curl_slist *grown = curl_slist_append(list, header);
            free(header);
            if (grown == NULL) {
                const char message[] = "Out of memory while preparing headers.";
                *error = axis_copy_string(message, sizeof(message) - 1);
                curl_slist_free_all(list);
                return NULL;
            }
            list = grown;
        }
        line = end == NULL ? NULL : end + 1;
    }
    return list;
}

int axis_http_request(
    AxisHttpClient *client,
    const char *method,
    const char *url,
    const char *body,
    const char *headers,
    long timeout_ms,
    AxisHttpResponse *response
) {
    if (client == NULL || method == NULL || url == NULL || response == NULL) {
        return 1;
    }
    memset(response, 0, sizeof(*response));

    CURL *curl = client->easy;
    curl_easy_reset(curl);

    char *header_error = NULL;
    struct curl_slist *header_list = axis_headers(headers, &header_error);
    if (header_error != NULL) {
        response->error = header_error;
        return 1;
    }

    AxisBuffer buffer = {0};
    CURLcode result = CURLE_OK;
#define AXIS_SETOPT(option, value) \
    do { \
        if (result == CURLE_OK) { \
            result = curl_easy_setopt(curl, option, value); \
        } \
    } while (0)
    AXIS_SETOPT(CURLOPT_URL, url);
    AXIS_SETOPT(CURLOPT_CUSTOMREQUEST, method);
    AXIS_SETOPT(CURLOPT_FOLLOWLOCATION, 1L);
    AXIS_SETOPT(CURLOPT_MAXREDIRS, 5L);
    AXIS_SETOPT(CURLOPT_CONNECTTIMEOUT_MS, timeout_ms);
    AXIS_SETOPT(CURLOPT_TIMEOUT_MS, timeout_ms);
    AXIS_SETOPT(CURLOPT_USERAGENT, "Axis");
    AXIS_SETOPT(CURLOPT_WRITEFUNCTION, axis_write_body);
    AXIS_SETOPT(CURLOPT_WRITEDATA, &buffer);
    AXIS_SETOPT(CURLOPT_HEADERFUNCTION, axis_write_header);
    AXIS_SETOPT(CURLOPT_HEADERDATA, response);
    if (header_list != NULL) {
        AXIS_SETOPT(CURLOPT_HTTPHEADER, header_list);
    }
    if (body != NULL) {
        AXIS_SETOPT(CURLOPT_POSTFIELDS, body);
        AXIS_SETOPT(CURLOPT_POSTFIELDSIZE, (long)strlen(body));
    }
#undef AXIS_SETOPT

    if (result == CURLE_OK) {
        result = curl_easy_perform(curl);
    }
    if (result == CURLE_OK) {
        result = curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &response->status);
    }
    if (result != CURLE_OK) {
        response->error = axis_copy_string(curl_easy_strerror(result), strlen(curl_easy_strerror(result)));
    } else {
        response->body = buffer.data;
        response->body_length = buffer.length;
        buffer.data = NULL;
    }

    free(buffer.data);
    curl_slist_free_all(header_list);
    return result == CURLE_OK ? 0 : 1;
}

void axis_http_response_free(AxisHttpResponse *response) {
    if (response == NULL) {
        return;
    }
    free(response->body);
    free(response->link_header);
    free(response->error);
    memset(response, 0, sizeof(*response));
}
