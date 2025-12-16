import { html, toggle } from './common.js';

export async function fetchReportJSONL(report_name) {
    const url = `/logs/${encodeURIComponent(report_name)}.jsonl`;
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const text = await response.text();
    return text
        .split('\n')
        .filter(line => line.trim().length > 0)
        .map(line => JSON.parse(line));
}

function getErrorKey(errorObj) {
    if (!errorObj.exception?.traceback?.length) {
        return null;
    }
    const lastFrame = errorObj.exception.traceback[errorObj.exception.traceback.length - 1];
    let key = `${lastFrame.filename}:${lastFrame.lineno}:${lastFrame.name}`;

    // For HTTPError, include the error code (first word of message) in the key
    if (errorObj.exception?.$class?.includes('HTTPError')) {
        const message = errorObj.exception.message ?? errorObj.exception.args;
        if (message) {
            const messageStr = Array.isArray(message) ? message[0] : message;
            const firstWord = messageStr.toString().split(/\s+/)[0];
            key += `:${firstWord}`;
        }
    }

    return key;
}

export function error_report(objects) {
    const errors = objects.filter(obj => obj.$class === 'paperoni.richlog:ErrorOccurred');

    const distinctErrors = new Map();
    errors.forEach(error => {
        const key = getErrorKey(error);
        if (key) {
            if (!distinctErrors.has(key)) {
                distinctErrors.set(key, {
                    error: error,
                    contexts: []
                });
            }
            if (error.context) {
                distinctErrors.get(key).contexts.push(error.context);
            }
        }
    });

    return Array.from(distinctErrors.entries()).map(([key, data]) => ({
        key: key,
        exception_type: data.error.exception.$class,
        message: data.error.exception.message ?? data.error.exception.args,
        contexts: data.contexts,
        occurrences: data.contexts.length,
        traceback: data.error.exception.traceback
    }));
}

function formatErrorAsHTML(errorSummary) {
    const exceptionName = errorSummary.exception_type.split(':').pop() ?? errorSummary.exception_type;
    const occurrenceText = `(${errorSummary.occurrences} occurrence${errorSummary.occurrences !== 1 ? 's' : ''})`;

    // Build contexts list items using array interpolation
    const contextItems = errorSummary.contexts.map(context => {
        if (Array.isArray(context)) {
            // Build breadcrumb elements using flatMap for arrays
            const breadcrumbParts = context.flatMap((item, index) => {
                const parts = [];
                if (index > 0) {
                    parts.push(html`<span class="breadcrumb-separator"> › </span>`);
                }

                const colonIndex = item.indexOf(':');
                if (colonIndex !== -1) {
                    const prefix = item.substring(0, colonIndex);
                    const text = item.substring(colonIndex + 1);
                    parts.push(html`<span class="breadcrumb-item context-${prefix}">${text}</span>`);
                } else {
                    parts.push(html`<span class="breadcrumb-item">${item}</span>`);
                }
                return parts;
            });

            return html`<li><div class="breadcrumb">${breadcrumbParts}</div></li>`;
        } else {
            return html`<li>${context}</li>`;
        }
    });

    const tracebackText = errorSummary.traceback.map(frame => {
        let text = `  ${frame.filename}:${frame.lineno} in ${frame.name}`;
        if (frame.line) {
            text += `\n    ${frame.line}`;
        }
        return text;
    }).join('\n');

    return toggle`
        <div class="error-report">
            <div class="error-header" toggler>
                <div class="error-header-content">
                    <div class="error-header-title">
                        <strong class="error-exception-name">${exceptionName}</strong>
                        <span class="error-occurrence-count">${occurrenceText}</span>
                    </div>
                    <div class="error-header-message">${errorSummary.message}</div>
                </div>
                <span class="item-toggle">▶</span>
            </div>
            <div class="error-content" toggled>
                <ul class="error-contexts-list">${contextItems}</ul>
                <p class="error-detail-section"><strong>Traceback:</strong></p>
                <pre class="error-traceback">${tracebackText}</pre>
            </div>
        </div>
    `;
}

function createStatisticsTable(objects) {
    const statistics = objects.filter(obj => obj.$class === 'paperoni.richlog:Statistic');

    if (statistics.length === 0) {
        return null;
    }

    // Keep only the last entry for each statistic name
    const latestStats = new Map();
    statistics.forEach(stat => {
        latestStats.set(stat.name, stat);
    });

    const rows = Array.from(latestStats.values()).map(stat =>
        html`<tr><td>${stat.name}</td><td>${stat.value}</td></tr>`
    );

    return html`<div class="statistics-section">
        <table class="statistics-table">
            <tbody>${rows}</tbody>
        </table>
    </div>`;
}

function createProgressiveCountsTable(objects) {
    const progressiveCounts = objects.filter(obj => obj.$class === 'paperoni.richlog:ProgressiveCount');

    if (progressiveCounts.length === 0) {
        return null;
    }

    // Group by category and origin
    const categoryData = new Map();
    progressiveCounts.forEach(pc => {
        if (!categoryData.has(pc.category)) {
            categoryData.set(pc.category, {
                total: 0,
                byOrigin: new Map()
            });
        }
        const data = categoryData.get(pc.category);
        data.total += pc.count;

        if (!data.byOrigin.has(pc.origin)) {
            data.byOrigin.set(pc.origin, 0);
        }
        data.byOrigin.set(pc.origin, data.byOrigin.get(pc.origin) + pc.count);
    });

    // Sort categories by total count (descending)
    const sortedCategories = Array.from(categoryData.entries()).sort((a, b) => b[1].total - a[1].total);

    const rows = sortedCategories.map(([category, data]) => {
        // Create detail row for origin breakdown
        const sortedOrigins = Array.from(data.byOrigin.entries()).sort((a, b) => b[1] - a[1]);
        const originRows = sortedOrigins.map(([origin, count]) =>
            html`<tr><td>${origin}</td><td>${count}</td></tr>`
        );

        return toggle`
            <tr class="category-row" toggler>
                <td class="category-cell">
                    <span class="item-toggle">▶</span> ${category}
                </td>
                <td>${data.total}</td>
            </tr>
            <tr class="category-detail-row" toggled>
                <td colspan="2">
                    <table class="origin-breakdown-table">
                        <tbody>${originRows}</tbody>
                    </table>
                </td>
            </tr>
        `;
    });

    return html`
        <div class="progressive-counts-section">
            <table class="progressive-counts-table">
                <tbody>${rows}</tbody>
            </table>
        </div>
    `;
}

function formatDateTime(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
}

function getCommandClassSequence(command) {
    const classes = [];
    let current = command;

    while (current) {
        if (current.$class) {
            classes.push(current.$class);
        }
        // Look for nested command in common field names
        if (current.command) {
            current = current.command;
        } else if (current.subcommand) {
            current = current.subcommand;
        } else {
            break;
        }
    }

    return classes.join(' › ');
}

function createCommandDescriptionSection(objects) {
    const commandDescs = objects.filter(obj => obj.$class === 'paperoni.__main__:CommandDescription');

    if (commandDescs.length === 0) {
        return null;
    }

    const commandDivs = commandDescs.map(desc => {
        const commandSequence = getCommandClassSequence(desc.command);
        const jsonText = JSON.stringify(desc.command, null, 2);

        return toggle`
            <div class="command-header" toggler>
                <div class="command-header-content"><strong>Command:</strong> ${commandSequence}</div>
                <span class="item-toggle">▶</span>
            </div>
            <div class="command-content" toggled>
                <pre class="command-json">${jsonText}</pre>
            </div>
        `;
    });

    return html`<div class="command-description-section">${commandDivs}</div>`;
}

function createLogHeader(objects, report_name) {
    const link = html`<a href="/logs/${encodeURIComponent(report_name)}.jsonl">${report_name}</a>`;
    const title = html`<h1 class="log-title">${link}</h1>`;

    if (objects.length === 0) {
        // Empty log - show only title with running indicator
        title.appendChild(html`<span class="running-indicator"> (still running)</span>`);
        return html`<div class="log-header">${title}</div>`;
    }

    // Check if there's a TimeStamp with label="end"
    const hasEndTimestamp = objects.some(obj =>
        obj.$class === 'paperoni.richlog:TimeStamp' && obj.label === 'end'
    );

    const firstTimestamp = new Date(objects[0].timestamp);
    const lastTimestamp = new Date(objects[objects.length - 1].timestamp);

    // If still running, use current time for duration calculation
    const endTimeForDuration = hasEndTimestamp ? lastTimestamp : new Date();
    const durationMs = endTimeForDuration - firstTimestamp;

    // Convert duration to hh:mm:ss
    const hours = Math.floor(durationMs / (1000 * 60 * 60));
    const minutes = Math.floor((durationMs % (1000 * 60 * 60)) / (1000 * 60));
    const seconds = Math.floor((durationMs % (1000 * 60)) / 1000);
    const durationStr = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;

    if (!hasEndTimestamp) {
        title.appendChild(html`<span class="running-indicator"> (still running)</span>`);
    }

    const endLabel = hasEndTimestamp ? 'End' : 'Last log entry';
    const startStr = formatDateTime(firstTimestamp);
    const endStr = formatDateTime(lastTimestamp);
    const timeInfo = html`<div class="log-time-info"><strong>Start:</strong> ${startStr} | <strong>${endLabel}:</strong> ${endStr} | <strong>Duration:</strong> ${durationStr}</div>`;

    return html`<div class="log-header">${title}${timeInfo}</div>`;
}

export async function main(report_name) {
    try {
        const objects = await fetchReportJSONL(report_name);

        // Create error reports
        const report = error_report(objects);
        report.sort((a, b) => b.occurrences - a.occurrences);

        const errorReports = report.map(errorSummary => formatErrorAsHTML(errorSummary));

        // Build entire container at once using arrays and null handling
        const container = html`<div id="error-reports-container">
            ${createLogHeader(objects, report_name)}
            ${createCommandDescriptionSection(objects)}
            ${createStatisticsTable(objects)}
            ${createProgressiveCountsTable(objects)}
            <h2 class="error-summary">Found ${report.length} distinct errors</h2>
            ${errorReports}
        </div>`;

        document.body.appendChild(container);
    } catch (err) {
        console.error("Failed to fetch report:", err);
        const container = html`<div id="error-reports-container">
            <div class="error-message">Error loading report: ${err.message}</div>
        </div>`;
        document.body.appendChild(container);
    }
}
