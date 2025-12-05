
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
    if (!errorObj.exception || !errorObj.exception.traceback || errorObj.exception.traceback.length === 0) {
        return null;
    }
    const lastFrame = errorObj.exception.traceback[errorObj.exception.traceback.length - 1];
    let key = `${lastFrame.filename}:${lastFrame.lineno}:${lastFrame.name}`;

    // For HTTPError, include the error code (first word of message) in the key
    if (errorObj.exception.$class && errorObj.exception.$class.includes('HTTPError')) {
        const message = errorObj.exception.message || errorObj.exception.args;
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
        message: data.error.exception.message || data.error.exception.args,
        contexts: data.contexts,
        occurrences: data.contexts.length,
        traceback: data.error.exception.traceback
    }));
}

function formatErrorAsHTML(errorSummary) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-report';

    const header = document.createElement('div');
    header.className = 'error-header';

    const headerContent = document.createElement('div');
    headerContent.className = 'error-header-content';

    const headerTitle = document.createElement('div');
    headerTitle.className = 'error-header-title';
    const exceptionName = errorSummary.exception_type.split(':').pop() || errorSummary.exception_type;
    headerTitle.innerHTML = `<strong class="error-exception-name">${exceptionName}</strong> <span class="error-occurrence-count">(${errorSummary.occurrences} occurrence${errorSummary.occurrences !== 1 ? 's' : ''})</span>`;
    headerContent.appendChild(headerTitle);

    const headerMessage = document.createElement('div');
    headerMessage.className = 'error-header-message';
    headerMessage.textContent = errorSummary.message;
    headerContent.appendChild(headerMessage);

    header.appendChild(headerContent);

    const toggle = document.createElement('span');
    toggle.className = 'error-toggle';
    toggle.textContent = '▶';
    header.appendChild(toggle);

    const content = document.createElement('div');
    content.className = 'error-content';

    // const exceptionType = document.createElement('p');
    // exceptionType.className = 'error-detail-section';
    // exceptionType.innerHTML = `<strong>Exception Type:</strong> ${errorSummary.exception_type}`;
    // content.appendChild(exceptionType);

    // const message = document.createElement('p');
    // message.className = 'error-detail-section';
    // message.innerHTML = `<strong>Message:</strong> ${JSON.stringify(errorSummary.message)}`;
    // content.appendChild(message);

    // const occurrences = document.createElement('p');
    // occurrences.className = 'error-detail-section';
    // occurrences.innerHTML = `<strong>Occurrences:</strong> ${errorSummary.occurrences}`;
    // content.appendChild(occurrences);

    if (errorSummary.contexts.length > 0) {
        // const contextsHeader = document.createElement('p');
        // contextsHeader.className = 'error-detail-section';
        // contextsHeader.innerHTML = '<strong>Contexts:</strong>';
        // content.appendChild(contextsHeader);

        const contextsList = document.createElement('ul');
        contextsList.className = 'error-contexts-list';
        errorSummary.contexts.forEach(context => {
            const contextItem = document.createElement('li');

            // If context is an array (dynamic_trace), display as breadcrumbs
            if (Array.isArray(context)) {
                const breadcrumbDiv = document.createElement('div');
                breadcrumbDiv.className = 'breadcrumb';

                context.forEach((item, index) => {
                    if (index > 0) {
                        const separator = document.createElement('span');
                        separator.className = 'breadcrumb-separator';
                        separator.textContent = ' › ';
                        breadcrumbDiv.appendChild(separator);
                    }

                    const crumb = document.createElement('span');
                    crumb.className = 'breadcrumb-item';

                    // Extract prefix before first colon and apply as CSS class
                    const colonIndex = item.indexOf(':');
                    if (colonIndex !== -1) {
                        const prefix = item.substring(0, colonIndex);
                        crumb.classList.add(`context-${prefix}`);
                        // Display only the part after the colon
                        crumb.textContent = item.substring(colonIndex + 1);
                    } else {
                        // No colon found, display the whole item
                        crumb.textContent = item;
                    }

                    breadcrumbDiv.appendChild(crumb);
                });

                contextItem.appendChild(breadcrumbDiv);
            } else {
                // Fallback for string contexts
                contextItem.textContent = context;
            }

            contextsList.appendChild(contextItem);
        });
        content.appendChild(contextsList);
    }

    const tracebackHeader = document.createElement('p');
    tracebackHeader.className = 'error-detail-section';
    tracebackHeader.innerHTML = '<strong>Traceback:</strong>';
    content.appendChild(tracebackHeader);

    const tracebackPre = document.createElement('pre');
    tracebackPre.className = 'error-traceback';
    const tracebackText = errorSummary.traceback.map(frame => {
        let text = `  ${frame.filename}:${frame.lineno} in ${frame.name}`;
        if (frame.line) {
            text += `\n    ${frame.line}`;
        }
        return text;
    }).join('\n');
    tracebackPre.textContent = tracebackText;
    content.appendChild(tracebackPre);

    header.addEventListener('click', () => {
        const isCollapsed = !content.classList.contains('expanded');
        content.classList.toggle('expanded');
        toggle.classList.toggle('expanded');
    });

    errorDiv.appendChild(header);
    errorDiv.appendChild(content);

    return errorDiv;
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

    const section = document.createElement('div');
    section.className = 'statistics-section';

    // const header = document.createElement('h2');
    // header.textContent = 'Statistics';
    // section.appendChild(header);

    const table = document.createElement('table');
    table.className = 'statistics-table';

    const tbody = document.createElement('tbody');
    Array.from(latestStats.values()).forEach(stat => {
        const row = document.createElement('tr');
        row.innerHTML = `<td>${stat.name}</td><td>${stat.value}</td>`;
        tbody.appendChild(row);
    });
    table.appendChild(tbody);

    section.appendChild(table);
    return section;
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

    const section = document.createElement('div');
    section.className = 'progressive-counts-section';

    // const header = document.createElement('h2');
    // header.textContent = 'Progressive Counts';
    // section.appendChild(header);

    const table = document.createElement('table');
    table.className = 'progressive-counts-table';

    const tbody = document.createElement('tbody');

    // Sort categories by total count (descending)
    const sortedCategories = Array.from(categoryData.entries()).sort((a, b) => b[1].total - a[1].total);

    sortedCategories.forEach(([category, data]) => {
        const row = document.createElement('tr');
        row.className = 'category-row';

        const categoryCell = document.createElement('td');
        categoryCell.className = 'category-cell';

        const toggle = document.createElement('span');
        toggle.className = 'category-toggle';
        toggle.textContent = '▶';
        categoryCell.appendChild(toggle);

        const categoryText = document.createElement('span');
        categoryText.textContent = ` ${category}`;
        categoryCell.appendChild(categoryText);

        row.appendChild(categoryCell);

        const countCell = document.createElement('td');
        countCell.textContent = data.total;
        row.appendChild(countCell);

        tbody.appendChild(row);

        // Create detail row for origin breakdown
        const detailRow = document.createElement('tr');
        detailRow.className = 'category-detail-row';

        const detailCell = document.createElement('td');
        detailCell.colSpan = 2;

        const detailTable = document.createElement('table');
        detailTable.className = 'origin-breakdown-table';

        const detailTbody = document.createElement('tbody');

        // Sort origins by count (descending)
        const sortedOrigins = Array.from(data.byOrigin.entries()).sort((a, b) => b[1] - a[1]);

        sortedOrigins.forEach(([origin, count]) => {
            const originRow = document.createElement('tr');
            originRow.innerHTML = `<td>${origin}</td><td>${count}</td>`;
            detailTbody.appendChild(originRow);
        });

        detailTable.appendChild(detailTbody);
        detailCell.appendChild(detailTable);
        detailRow.appendChild(detailCell);

        tbody.appendChild(detailRow);

        // Add click handler to toggle details
        row.addEventListener('click', () => {
            const isExpanded = detailRow.classList.contains('expanded');
            detailRow.classList.toggle('expanded');
            toggle.classList.toggle('expanded');
        });
    });

    table.appendChild(tbody);
    section.appendChild(table);
    return section;
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

    const section = document.createElement('div');
    section.className = 'command-description-section';

    commandDescs.forEach(desc => {
        const commandDiv = document.createElement('div');
        commandDiv.className = 'command-description';

        const header = document.createElement('div');
        header.className = 'command-header';

        const headerContent = document.createElement('div');
        headerContent.className = 'command-header-content';
        headerContent.innerHTML = `<strong>Command:</strong> ${getCommandClassSequence(desc.command)}`;
        header.appendChild(headerContent);

        const toggle = document.createElement('span');
        toggle.className = 'command-toggle';
        toggle.textContent = '▶';
        header.appendChild(toggle);

        const content = document.createElement('div');
        content.className = 'command-content';

        const pre = document.createElement('pre');
        pre.className = 'command-json';
        pre.textContent = JSON.stringify(desc.command, null, 2);

        content.appendChild(pre);

        header.addEventListener('click', () => {
            const isCollapsed = !content.classList.contains('expanded');
            content.classList.toggle('expanded');
            toggle.classList.toggle('expanded');
        });

        commandDiv.appendChild(header);
        commandDiv.appendChild(content);
        section.appendChild(commandDiv);
    });

    return section;
}

function createLogHeader(objects, report_name) {
    const header = document.createElement('div');
    header.className = 'log-header';

    const title = document.createElement('h1');
    title.className = 'log-title';
    const link = document.createElement('a');
    link.href = `/logs/${encodeURIComponent(report_name)}.jsonl`;
    link.textContent = report_name;
    title.appendChild(link);

    if (objects.length === 0) {
        // Empty log - show only title with running indicator
        const runningIndicator = document.createElement('span');
        runningIndicator.className = 'running-indicator';
        runningIndicator.textContent = ' (still running)';
        title.appendChild(runningIndicator);
        header.appendChild(title);
        return header;
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
        const runningIndicator = document.createElement('span');
        runningIndicator.className = 'running-indicator';
        runningIndicator.textContent = ' (still running)';
        title.appendChild(runningIndicator);
    }

    header.appendChild(title);

    const timeInfo = document.createElement('div');
    timeInfo.className = 'log-time-info';
    const endLabel = hasEndTimestamp ? 'End' : 'Last log entry';
    timeInfo.innerHTML = `<strong>Start:</strong> ${formatDateTime(firstTimestamp)} | <strong>${endLabel}:</strong> ${formatDateTime(lastTimestamp)} | <strong>Duration:</strong> ${durationStr}`;
    header.appendChild(timeInfo);

    return header;
}

export async function main(report_name) {
    const container = document.createElement('div');
    container.id = 'error-reports-container';

    try {
        const objects = await fetchReportJSONL(report_name);

        // Create log header with time info
        const logHeader = createLogHeader(objects, report_name);
        if (logHeader) {
            container.appendChild(logHeader);
        }

        // Create command description section
        const commandDescSection = createCommandDescriptionSection(objects);
        if (commandDescSection) {
            container.appendChild(commandDescSection);
        }

        // Create statistics tables
        const statisticsTable = createStatisticsTable(objects);
        if (statisticsTable) {
            container.appendChild(statisticsTable);
        }

        const progressiveCountsTable = createProgressiveCountsTable(objects);
        if (progressiveCountsTable) {
            container.appendChild(progressiveCountsTable);
        }

        // Create error reports
        const report = error_report(objects);

        // Sort by number of occurrences (descending)
        report.sort((a, b) => b.occurrences - a.occurrences);

        const summary = document.createElement('h2');
        summary.className = 'error-summary';
        summary.textContent = `Found ${report.length} distinct errors`;
        container.appendChild(summary);

        report.forEach(errorSummary => {
            const errorHTML = formatErrorAsHTML(errorSummary);
            container.appendChild(errorHTML);
        });

        document.body.appendChild(container);
    } catch (err) {
        console.error("Failed to fetch report:", err);
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.textContent = `Error loading report: ${err.message}`;
        container.appendChild(errorDiv);
        document.body.appendChild(container);
    }
}
