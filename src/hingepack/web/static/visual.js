function renderVisual(target, data) {
    const states = ['观察','候补','暂停','已分派'];
    const tally = new Map();
    data.rows.forEach(row => {
        if (!tally.has(row.zone)) tally.set(row.zone,Object.fromEntries(states.map(item => [item,0])));
        const bucket = tally.get(row.zone);
        if (row.state in bucket) bucket[row.state]++;
    });
    const table = rowsTable([...tally].map(([zone, counts]) => ({货型:zone,...counts})), ['货型',...states]);
    table.className = 'kit-board';
    for (const td of table.querySelectorAll('td:not(:first-child)')) {
        td.style.setProperty('--fill',`${Math.min(74,Number(td.textContent)*13)}%`);
    }
    target.append(table);
}
