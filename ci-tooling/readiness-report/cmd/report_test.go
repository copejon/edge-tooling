package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"testing"
	"time"
)

func TestBuildViewReportCountsTriagedAndUntriaged(t *testing.T) {
	generated := time.Date(2026, 8, 17, 4, 0, 0, 0, time.UTC)
	report := componentReport{
		GeneratedAt: &generated,
		Rows: []reportRow{
			{
				Component: "Etcd",
				Columns: []reportColumn{{
					RegressedTests: []regressedTest{
						{
							Component: "Etcd",
							TestName:  "triaged test A",
							Status:    -300,
							Regression: &regression{
								ID: 1,
								Triages: []triage{{
									ID:          10,
									URL:         "https://redhat.atlassian.net/browse/OCPBUGS-1",
									Description: "nested only",
									Type:        "test",
								}},
							},
						},
						{
							Component: "Etcd",
							TestName:  "triaged test B",
							Status:    -1000,
							Regression: &regression{
								ID: 2,
								Triages: []triage{{
									ID: 10,
								}},
							},
						},
						{
							Component: "Etcd",
							TestName:  "untriaged test",
							Status:    -500,
							Regression: &regression{
								ID:      3,
								Triages: []triage{},
							},
						},
					},
				}},
			},
		},
	}
	triages := []triage{{
		ID:          10,
		URL:         "https://redhat.atlassian.net/browse/OCPBUGS-1",
		Description: "from triage API",
		Type:        "product",
		Bug:         &bug{Key: "OCPBUGS-1", URL: "https://redhat.atlassian.net/browse/OCPBUGS-1"},
	}}

	got := buildViewReport("https://sippy.example", "5.0-ha-vs-two-node-fencing", report, triages)
	if got.Regressed != 3 || got.Triaged != 2 || got.Untriaged != 1 {
		t.Fatalf("counts: regressed=%d triaged=%d untriaged=%d", got.Regressed, got.Triaged, got.Untriaged)
	}
	if len(got.Triages) != 1 {
		t.Fatalf("unique triages: %d", len(got.Triages))
	}
	tr := got.Triages[0]
	if tr.Tests != 2 {
		t.Fatalf("triage test count: %d", tr.Tests)
	}
	if tr.Jira != "OCPBUGS-1" {
		t.Fatalf("jira key: %s", tr.Jira)
	}
	if tr.Type != "product" {
		t.Fatalf("type should prefer triage API: %s", tr.Type)
	}
	if tr.View != "two-node-fencing" {
		t.Fatalf("short view: %s", tr.View)
	}
	if !strings.HasSuffix(tr.TriageURL, "/sippy-ng/component_readiness/triages/10") {
		t.Fatalf("triage url: %s", tr.TriageURL)
	}
}

func TestResolveViewsPrefersReleasePrefix(t *testing.T) {
	available := []string{
		"5.0-ha-vs-two-node-fencing",
		"5.0-ha-vs-single",
		"4.22-ha-vs-two-node-fencing",
	}
	got := resolveViews("5.0", "ha-vs-two-node-fencing,ha-vs-missing", available)
	if len(got) != 1 || got[0] != "5.0-ha-vs-two-node-fencing" {
		t.Fatalf("got %v", got)
	}

	got = resolveViews("4.22", "5.0-ha-vs-two-node-fencing", available)
	if len(got) != 1 || got[0] != "5.0-ha-vs-two-node-fencing" {
		t.Fatalf("full name should match exactly, got %v", got)
	}
}

func TestJiraKeyFromURL(t *testing.T) {
	key := jiraKey(triage{URL: "https://redhat.atlassian.net/browse/OCPBUGS-104544"})
	if key != "OCPBUGS-104544" {
		t.Fatalf("got %s", key)
	}
}

func TestBuildViewReportCountsDistinctVariantsWithoutRegressionID(t *testing.T) {
	report := componentReport{
		Rows: []reportRow{{
			Component: "Etcd",
			Columns: []reportColumn{{
				RegressedTests: []regressedTest{
					{TestID: "t1", Component: "Etcd", TestName: "same test", Variants: map[string]string{"Upgrade": "major"}, Status: -500},
					{TestID: "t1", Component: "Etcd", TestName: "same test", Variants: map[string]string{"Upgrade": "micro"}, Status: -400},
					{TestID: "t1", Component: "Etcd", TestName: "same test", Variants: map[string]string{"Upgrade": "major"}, Status: -500},
				},
			}},
		}},
	}
	got := buildViewReport("https://sippy.example", "5.0-ha-vs-single", report, nil)
	if got.Regressed != 2 || got.Untriaged != 2 || got.Triaged != 0 {
		t.Fatalf("counts: regressed=%d triaged=%d untriaged=%d", got.Regressed, got.Triaged, got.Untriaged)
	}
}

func TestGetJSONValidJSON(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"name":"ok"}`))
	}))
	defer srv.Close()

	var got struct {
		Name string `json:"name"`
	}
	if err := getJSON(context.Background(), srv.Client(), srv.URL, &got); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.Name != "ok" {
		t.Fatalf("got %+v", got)
	}
}

func TestGetJSONMalformedJSON(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{not json`))
	}))
	defer srv.Close()

	var dest map[string]string
	err := getJSON(context.Background(), srv.Client(), srv.URL, &dest)
	if err == nil {
		t.Fatal("expected decode error")
	}
	if !strings.Contains(err.Error(), "decode") {
		t.Fatalf("expected decode error, got %v", err)
	}
}

func TestGetJSONNon200(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "nope", http.StatusInternalServerError)
	}))
	defer srv.Close()

	var dest map[string]string
	err := getJSON(context.Background(), srv.Client(), srv.URL, &dest)
	if err == nil {
		t.Fatal("expected HTTP error")
	}
	if !strings.Contains(err.Error(), "HTTP 500") {
		t.Fatalf("expected HTTP 500, got %v", err)
	}
}

func TestSplitCSV(t *testing.T) {
	got := splitCSV("ha-vs-single, ha-vs-two-node-fencing")
	want := []string{"ha-vs-single", "ha-vs-two-node-fencing"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("normal values: got %v, want %v", got, want)
	}

	got = splitCSV("a,, ,b,")
	want = []string{"a", "b"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("empty entries: got %v, want %v", got, want)
	}

	got = splitCSV("")
	if len(got) != 0 {
		t.Fatalf("empty input: got %v", got)
	}
}

func TestJiraKeyValidAndMalformedURLs(t *testing.T) {
	got := jiraKey(triage{URL: "https://redhat.atlassian.net/browse/OCPBUGS-1"})
	if got != "OCPBUGS-1" {
		t.Fatalf("valid URL: got %s", got)
	}

	raw := "http://%"
	got = jiraKey(triage{URL: raw})
	if got != raw {
		t.Fatalf("malformed URL should be returned as-is, got %s", got)
	}
}

func TestLatestGeneratedAt(t *testing.T) {
	if got := latestGeneratedAt(nil); got != "unknown" {
		t.Fatalf("empty reports: got %s", got)
	}
	if got := latestGeneratedAt([]viewReport{{}, {GeneratedAt: nil}}); got != "unknown" {
		t.Fatalf("all nil: got %s", got)
	}

	earlier := time.Date(2026, 8, 1, 12, 0, 0, 0, time.UTC)
	later := time.Date(2026, 8, 17, 4, 0, 0, 0, time.UTC)
	got := latestGeneratedAt([]viewReport{
		{GeneratedAt: &earlier},
		{GeneratedAt: nil},
		{GeneratedAt: &later},
	})
	if got != "2026-08-17" {
		t.Fatalf("latest present date: got %s", got)
	}
}
