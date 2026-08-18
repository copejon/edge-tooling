package main

import (
	"bytes"
	"strings"
	"testing"
)

func TestHTTPOrHTTPSURL(t *testing.T) {
	tests := []struct {
		name   string
		raw    string
		wantOK bool
	}{
		{name: "https jira", raw: "https://redhat.atlassian.net/browse/OCPBUGS-1", wantOK: true},
		{name: "http jira", raw: "http://issues.example.com/browse/FOO-2", wantOK: true},
		{name: "javascript", raw: "javascript:alert(1)", wantOK: false},
		{name: "missing host", raw: "https:///browse/OCPBUGS-1", wantOK: false},
		{name: "unsupported scheme", raw: "ftp://redhat.atlassian.net/browse/OCPBUGS-1", wantOK: false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, ok := httpOrHTTPSURL(tt.raw)
			if ok != tt.wantOK {
				t.Fatalf("httpOrHTTPSURL(%q) ok=%v, want %v (got %q)", tt.raw, ok, tt.wantOK, got)
			}
			if tt.wantOK && got == "" {
				t.Fatalf("expected a URL string for %q", tt.raw)
			}
			if !tt.wantOK && got != "" {
				t.Fatalf("expected empty URL for %q, got %q", tt.raw, got)
			}
		})
	}
}

func TestWriteHTMLJiraLinkRequiresHTTPURL(t *testing.T) {
	reports := []viewReport{{
		View: "5.0-ha-vs-single",
		Triages: []triageSummary{
			{
				ID:        1,
				View:      "single",
				Tests:     1,
				Type:      "product",
				Jira:      "OCPBUGS-1",
				JiraURL:   "https://redhat.atlassian.net/browse/OCPBUGS-1",
				TriageURL: "https://sippy.example/sippy-ng/component_readiness/triages/1",
			},
			{
				ID:        2,
				View:      "single",
				Tests:     1,
				Type:      "product",
				Jira:      "OCPBUGS-2",
				JiraURL:   "javascript:alert(1)",
				TriageURL: "https://sippy.example/sippy-ng/component_readiness/triages/2",
			},
		},
	}}
	var buf bytes.Buffer
	writeHTML(&buf, "5.0", reports, false)
	out := buf.String()

	if !strings.Contains(out, `href="https://redhat.atlassian.net/browse/OCPBUGS-1"`) {
		t.Fatalf("expected safe jira link, got %s", out)
	}
	if strings.Contains(strings.ToLower(out), "javascript:") {
		t.Fatalf("javascript url should not be linked: %s", out)
	}
	if !strings.Contains(out, "OCPBUGS-2") {
		t.Fatalf("expected escaped jira text for unsafe url, got %s", out)
	}
}
