function main() {
    res = getStats();
    initInterface(res);
    seconds = 10;
    interval = seconds * 1000;
    update = function() {
        res = getStats();
        updateInterface(res);
    }
    setInterval(update, interval);
}


function getStats() {
    xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/getStats', false);
    xhr.send();
    msg = JSON.parse(xhr.responseText);
    if (xhr.status != 200) {
        alert('Oops... some error occurred. Check console log, then reload the page');
        console.log(res);
    }
    return msg;
}


function sortTeams(teams) {
    teams.sort(function(t1, t2) {
        if (t2.overall_score == t1.overall_score) {
            return t1.last_pts_update - t2.last_pts_update;
        } else {
            return t2.overall_score - t1.overall_score;
        }
    })
}


function expectedSla(roundNum, flagLifetime) {
    n = 0;
    for (r=0; r<roundNum; r++) {
        if ((r+1) <= flagLifetime) {
            n = n + r + 1;
        } else {
            n = n + flagLifetime + 1;
        }
    }
    return n;
}


function getSlaPercentage(obtained, expected) {
    if (obtained < 0) {
        obtained = 0;
    }
    perc = (obtained / expected) * 100;
    perc = perc.toFixed(2);
    return perc;
}


function colorForStatus(status) {
    colors = {"ok": "lime", "corrupt": "orchid", "mumble": "orange", "down": "red", "error": "yellow"};
    return colors[status];
}


function initInterface(response) {
    round = document.getElementById("roundNum");
    round.textContent = "Round: " + response['roundNum'];
    legend = document.getElementById("legend");
    for (i=0; i<legend.childElementCount; i++) {
        cell = legend.children[i];
        cell.style.backgroundColor = colorForStatus(cell.textContent);
        cell.textContent = cell.textContent.toUpperCase();
    }
    services = Object.keys(response['teams'][0]['points']);
    header = document.getElementById("teamsHeader");
    for (i=0; i<services.length; i++) {
        th = document.createElement("th");
        th.textContent = services[i];
        header.appendChild(th);
    }
    table = document.getElementById("teams");
    sortTeams(response['teams']);
    teams = response['teams'];
    maxSla = expectedSla(response['roundNum'], response['flagLifetime']);
    firstPlacesColors = ["gold", "silver", "goldenrod"];
    for (i=0; i<teams.length; i++) {
        tr = document.createElement("tr");
        tr.setAttribute("id", "row_"+i);
        td = document.createElement("td");
        td.textContent = i+1;
        if (i < firstPlacesColors.length) {
            td.style.backgroundColor = firstPlacesColors[i];
        }
        tr.appendChild(td)
        td = document.createElement("td");
        td.textContent = teams[i]['name'];
        if (i < firstPlacesColors.length) {
            td.style.backgroundColor = firstPlacesColors[i];
        }
        tr.appendChild(td);
        td = document.createElement("td");
        td.textContent = teams[i]['ip_addr'];
        if (i < firstPlacesColors.length) {
            td.style.backgroundColor = firstPlacesColors[i];
        }
        tr.appendChild(td);
        td = document.createElement("td");
        td.textContent = teams[i]['overall_score'];
        if (i < firstPlacesColors.length) {
            td.style.backgroundColor = firstPlacesColors[i];
        }
        tr.appendChild(td);
        points = teams[i]['points'];
        serviceStatus = teams[i]['service_status'];
        for (j=0; j<services.length; j++) {
            servicePts = points[services[j]];
            td = document.createElement("td");
            td.innerHTML = "SLA percentage: " + getSlaPercentage(servicePts['sla_pts'], maxSla) + '%<br>';
            td.innerHTML += "SLA checks: " + servicePts['sla_pts'] + '<br>';
            td.innerHTML += 'Flags: +' + servicePts['atk_pts'] + '/' + servicePts['def_pts'];
            status = serviceStatus[services[j]];
            td.style.backgroundColor = colorForStatus(status);
            td.style.textAlign = 'left';
            tr.appendChild(td);
        }
        table.appendChild(tr);
    }
    document.body.className = 'visible';
}


function updateInterface(response) {
    round = document.getElementById("roundNum");
    round.textContent = "Round: " + response['roundNum'];
    services = Object.keys(response['teams'][0]['points']);
    table = document.getElementById("teams");
    sortTeams(response['teams']);
    teams = response['teams'];
    maxSla = expectedSla(response['roundNum'], response['flagLifetime']);
    for (i=0; i<teams.length; i++) {
        tr = document.getElementById("row_"+i);
        td = tr.children[1];
        td.textContent = teams[i]['name'];
        td = tr.children[2];
        td.textContent = teams[i]['ip_addr'];
        td = tr.children[3];
        td.textContent = teams[i]['overall_score'];
        points = teams[i]['points'];
        serviceStatus = teams[i]['service_status'];
        for (j=0; j<services.length; j++) {
            servicePts = points[services[j]];
            td = tr.children[4+j];
            td.innerHTML = "SLA percentage: " + getSlaPercentage(servicePts['sla_pts'], maxSla) + '%<br>';
            td.innerHTML += "SLA checks: " + servicePts['sla_pts'] + '<br>';
            td.innerHTML += 'Flags: +' + servicePts['atk_pts'] + '/' + servicePts['def_pts'];
            status = serviceStatus[services[j]];
            td.style.backgroundColor = colorForStatus(status);
        }
    }
}
