package com.pension.common.dto;

import java.time.Instant;
import java.util.List;

public record ErrorResponseBody(
        ErrorDetail error
) {
    public record ErrorDetail(
            String code,
            String message,
            Instant timestamp,
            List<String> details
    ) {}

    public static ErrorResponseBody of(String code, String message, List<String> details) {
        return new ErrorResponseBody(new ErrorDetail(code, message, Instant.now(), details));
    }

    public static ErrorResponseBody of(String code, String message) {
        return of(code, message, List.of());
    }
}