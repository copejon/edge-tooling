package main

import (
	"fmt"
	"html"
	"io"
	"net/url"
	"strings"
)

func writeTSV(w io.Writer, release string, reports []viewReport, includeUntriaged bool) {
	fmt.Fprintf(w, "Component Readiness — %s — %s\n\n", release, latestGeneratedAt(reports))
	fmt.Fprintln(w, "SUMMARY")
	fmt.Fprintln(w, strings.Join([]string{"View", "Regressed", "Untriaged", "Triaged", "View link"}, "\t"))
	for _, r := range reports {
		fmt.Fprintf(w, "%s\t%d\t%d\t%d\t%s\n", shortView(r.View), r.Regressed, r.Untriaged, r.Triaged, r.ViewURL)
	}

	anyTriages := false
	for _, r := range reports {
		if len(r.Triages) > 0 {
			anyTriages = true
			break
		}
	}
	if anyTriages {
		fmt.Fprintln(w)
		fmt.Fprintln(w, "TRIAGED")
		fmt.Fprintln(w, strings.Join([]string{"View", "Tests", "Type", "JIRA", "Status", "Triage"}, "\t"))
		for _, r := range reports {
			for _, t := range r.Triages {
				jira := t.Jira
				if t.JiraURL != "" {
					jira = t.JiraURL
				}
				fmt.Fprintf(w, "%s\t%d\t%s\t%s\t%s\t%s\n", t.View, t.Tests, t.Type, jira, resolvedLabel(t.Resolved), t.TriageURL)
			}
		}
	}

	if includeUntriaged {
		writeUntriagedTSV(w, reports)
	}
}

func writeUntriagedTSV(w io.Writer, reports []viewReport) {
	any := false
	for _, r := range reports {
		if len(r.UntriagedTests) > 0 {
			any = true
			break
		}
	}
	if !any {
		return
	}
	fmt.Fprintln(w)
	fmt.Fprintln(w, "UNTRIAGED")
	fmt.Fprintln(w, strings.Join([]string{"View", "Component", "Status", "Test"}, "\t"))
	for _, r := range reports {
		for _, t := range r.UntriagedTests {
			name := t.TestName
			if t.Variants != "" {
				name = t.TestName + " (" + t.Variants + ")"
			}
			fmt.Fprintf(w, "%s\t%s\t%s\t%s\n", t.View, t.Component, t.Status, name)
		}
	}
}

func writeMarkdown(w io.Writer, release string, reports []viewReport, includeUntriaged bool) {
	fmt.Fprintf(w, "# Component Readiness — %s — %s\n\n", release, latestGeneratedAt(reports))
	fmt.Fprintln(w, "| View | Regressed | Untriaged | Triaged |")
	fmt.Fprintln(w, "| --- | ---: | ---: | ---: |")
	for _, r := range reports {
		fmt.Fprintf(w, "| [%s](%s) | %d | %d | %d |\n", shortView(r.View), r.ViewURL, r.Regressed, r.Untriaged, r.Triaged)
	}

	anyTriages := false
	for _, r := range reports {
		if len(r.Triages) > 0 {
			anyTriages = true
			break
		}
	}
	if anyTriages {
		fmt.Fprintln(w)
		fmt.Fprintln(w, "## Triaged")
		fmt.Fprintln(w)
		fmt.Fprintln(w, "| View | Tests | Type | JIRA | Status | Triage |")
		fmt.Fprintln(w, "| --- | ---: | --- | --- | --- | --- |")
		for _, r := range reports {
			for _, t := range r.Triages {
				jira := t.Jira
				if t.JiraURL != "" && t.Jira != "" {
					jira = fmt.Sprintf("[%s](%s)", t.Jira, t.JiraURL)
				} else if t.JiraURL != "" {
					jira = t.JiraURL
				}
				triage := fmt.Sprintf("[%d](%s)", t.ID, t.TriageURL)
				fmt.Fprintf(w, "| %s | %d | %s | %s | %s | %s |\n", t.View, t.Tests, t.Type, jira, resolvedLabel(t.Resolved), triage)
			}
		}
	}

	if includeUntriaged {
		writeUntriagedMarkdown(w, reports)
	}
}

func writeUntriagedMarkdown(w io.Writer, reports []viewReport) {
	any := false
	for _, r := range reports {
		if len(r.UntriagedTests) > 0 {
			any = true
			break
		}
	}
	if !any {
		return
	}
	fmt.Fprintln(w)
	fmt.Fprintln(w, "## Untriaged")
	fmt.Fprintln(w)
	fmt.Fprintln(w, "| View | Component | Status | Test |")
	fmt.Fprintln(w, "| --- | --- | --- | --- |")
	for _, r := range reports {
		for _, t := range r.UntriagedTests {
			name := t.TestName
			if t.Variants != "" {
				name = t.TestName + " (" + t.Variants + ")"
			}
			fmt.Fprintf(w, "| %s | %s | %s | %s |\n", t.View, t.Component, t.Status, escapePipes(name))
		}
	}
}

func writeHTML(w io.Writer, release string, reports []viewReport, includeUntriaged bool) {
	fmt.Fprintln(w, "<!DOCTYPE html>")
	fmt.Fprintln(w, "<html><head><meta charset=\"utf-8\"><title>Component Readiness</title></head><body>")
	fmt.Fprintf(w, "<p><b>Component Readiness — %s — %s</b></p>\n", html.EscapeString(release), html.EscapeString(latestGeneratedAt(reports)))

	fmt.Fprintln(w, "<table border=\"1\" cellpadding=\"4\" cellspacing=\"0\">")
	fmt.Fprintln(w, "<tr><th>View</th><th>Regressed</th><th>Untriaged</th><th>Triaged</th></tr>")
	for _, r := range reports {
		fmt.Fprintf(w, "<tr><td><a href=\"%s\">%s</a></td><td>%d</td><td>%d</td><td>%d</td></tr>\n",
			html.EscapeString(r.ViewURL), html.EscapeString(shortView(r.View)), r.Regressed, r.Untriaged, r.Triaged)
	}
	fmt.Fprintln(w, "</table>")

	anyTriages := false
	for _, r := range reports {
		if len(r.Triages) > 0 {
			anyTriages = true
			break
		}
	}
	if anyTriages {
		fmt.Fprintln(w, "<p><b>Triaged</b></p>")
		fmt.Fprintln(w, "<table border=\"1\" cellpadding=\"4\" cellspacing=\"0\">")
		fmt.Fprintln(w, "<tr><th>View</th><th>Tests</th><th>Type</th><th>JIRA</th><th>Status</th><th>Triage</th></tr>")
		for _, r := range reports {
			for _, t := range r.Triages {
				jira := html.EscapeString(t.Jira)
				if href, ok := httpOrHTTPSURL(t.JiraURL); ok {
					label := t.Jira
					if label == "" {
						label = t.JiraURL
					}
					jira = fmt.Sprintf("<a href=\"%s\">%s</a>", html.EscapeString(href), html.EscapeString(label))
				}
				fmt.Fprintf(w, "<tr><td>%s</td><td>%d</td><td>%s</td><td>%s</td><td>%s</td><td><a href=\"%s\">%d</a></td></tr>\n",
					html.EscapeString(t.View), t.Tests, html.EscapeString(t.Type), jira, resolvedLabel(t.Resolved),
					html.EscapeString(t.TriageURL), t.ID)
			}
		}
		fmt.Fprintln(w, "</table>")
	}

	if includeUntriaged {
		writeUntriagedHTML(w, reports)
	}
	fmt.Fprintln(w, "</body></html>")
}

func writeUntriagedHTML(w io.Writer, reports []viewReport) {
	any := false
	for _, r := range reports {
		if len(r.UntriagedTests) > 0 {
			any = true
			break
		}
	}
	if !any {
		return
	}
	fmt.Fprintln(w, "<p><b>Untriaged</b></p>")
	fmt.Fprintln(w, "<table border=\"1\" cellpadding=\"4\" cellspacing=\"0\">")
	fmt.Fprintln(w, "<tr><th>View</th><th>Component</th><th>Status</th><th>Test</th></tr>")
	for _, r := range reports {
		for _, t := range r.UntriagedTests {
			name := t.TestName
			if t.Variants != "" {
				name = t.TestName + " (" + t.Variants + ")"
			}
			fmt.Fprintf(w, "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>\n",
				html.EscapeString(t.View), html.EscapeString(t.Component), html.EscapeString(t.Status), html.EscapeString(name))
		}
	}
	fmt.Fprintln(w, "</table>")
}

func escapePipes(s string) string {
	return strings.ReplaceAll(s, "|", "\\|")
}

// httpOrHTTPSURL reports whether raw is an absolute http or https URL with a host.
func httpOrHTTPSURL(raw string) (string, bool) {
	u, err := url.Parse(raw)
	if err != nil {
		return "", false
	}
	scheme := strings.ToLower(u.Scheme)
	if scheme != "http" && scheme != "https" {
		return "", false
	}
	if u.Host == "" {
		return "", false
	}
	return u.String(), true
}
