package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"sort"
	"strings"
	"syscall"
	"time"
)

const (
	defaultBaseURL = "https://sippy.dptools.openshift.org"
	defaultRelease = "5.0"
)

var defaultViewSuffixes = []string{
	"ha-vs-two-node-fencing",
	"ha-vs-two-node-arbiter",
	"ha-vs-single",
}

func main() {
	release := flag.String("release", defaultRelease, "Release version to report on (for example 5.0, 4.22, 5.1)")
	baseURL := flag.String("base-url", defaultBaseURL, "Sippy base URL")
	viewsFlag := flag.String("views", "", "Comma-separated view suffixes or full view names. Default: ha-vs-two-node-fencing,ha-vs-two-node-arbiter,ha-vs-single")
	format := flag.String("format", "tsv", "Output format: tsv, md, or html")
	listViews := flag.Bool("list-views", false, "List Sippy views for the given release and exit")
	untriaged := flag.Bool("untriaged", false, "Include a table of untriaged regressed tests")
	flag.Parse()

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	client := &http.Client{Timeout: 120 * time.Second}

	available, err := fetchViewNames(ctx, client, *baseURL)
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to list views: %v\n", err)
		os.Exit(1)
	}

	if *listViews {
		printMatchingViews(available, *release)
		return
	}

	viewNames := resolveViews(*release, *viewsFlag, available)
	if len(viewNames) == 0 {
		fmt.Fprintf(os.Stderr, "no matching views for release %s\n", *release)
		os.Exit(1)
	}

	reports := make([]viewReport, 0, len(viewNames))
	for _, name := range viewNames {
		report, err := fetchViewReport(ctx, client, *baseURL, name)
		if err != nil {
			fmt.Fprintf(os.Stderr, "failed to fetch %s: %v\n", name, err)
			os.Exit(1)
		}
		reports = append(reports, report)
	}

	out := os.Stdout
	switch strings.ToLower(*format) {
	case "html":
		writeHTML(out, *release, reports, *untriaged)
	case "md", "markdown":
		writeMarkdown(out, *release, reports, *untriaged)
	case "tsv", "text", "docs":
		writeTSV(out, *release, reports, *untriaged)
	default:
		fmt.Fprintf(os.Stderr, "unknown format %q (use tsv, md, or html)\n", *format)
		os.Exit(1)
	}
}

func printMatchingViews(available []string, release string) {
	prefix := release + "-"
	found := false
	for _, name := range available {
		if strings.HasPrefix(name, prefix) {
			fmt.Println(name)
			found = true
		}
	}
	if !found {
		fmt.Fprintf(os.Stderr, "no views found for release %s\n", release)
		os.Exit(1)
	}
}

func resolveViews(release, viewsFlag string, available []string) []string {
	inputs := defaultViewSuffixes
	if strings.TrimSpace(viewsFlag) != "" {
		inputs = splitCSV(viewsFlag)
	}

	availableSet := make(map[string]struct{}, len(available))
	for _, name := range available {
		availableSet[name] = struct{}{}
	}

	var resolved []string
	for _, raw := range inputs {
		candidates := []string{raw}
		if !strings.HasPrefix(raw, release+"-") {
			candidates = append([]string{release + "-" + raw}, candidates...)
		}
		matched := ""
		for _, candidate := range candidates {
			if _, ok := availableSet[candidate]; ok {
				matched = candidate
				break
			}
		}
		if matched == "" {
			fmt.Fprintf(os.Stderr, "warning: view %s is not available, skipping\n", candidates[0])
			continue
		}
		resolved = append(resolved, matched)
	}
	return resolved
}

func splitCSV(s string) []string {
	parts := strings.Split(s, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

func fetchViewNames(ctx context.Context, client *http.Client, baseURL string) ([]string, error) {
	var views []struct {
		Name string `json:"name"`
	}
	if err := getJSON(ctx, client, baseURL+"/api/component_readiness/views", &views); err != nil {
		return nil, err
	}
	names := make([]string, 0, len(views))
	for _, v := range views {
		if v.Name != "" {
			names = append(names, v.Name)
		}
	}
	sort.Strings(names)
	return names, nil
}

func fetchViewReport(ctx context.Context, client *http.Client, baseURL, view string) (viewReport, error) {
	var report componentReport
	if err := getJSON(ctx, client, baseURL+"/api/component_readiness?view="+url.QueryEscape(view), &report); err != nil {
		return viewReport{}, err
	}

	var triages []triage
	if err := getJSON(ctx, client, baseURL+"/api/component_readiness/triages?view="+url.QueryEscape(view), &triages); err != nil {
		return viewReport{}, err
	}

	return buildViewReport(baseURL, view, report, triages), nil
}

func getJSON(ctx context.Context, client *http.Client, rawURL string, dest interface{}) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return err
	}
	req.Header.Set("Accept", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("HTTP %d from %s: %s", resp.StatusCode, rawURL, truncate(string(body), 300))
	}
	if err := json.Unmarshal(body, dest); err != nil {
		return fmt.Errorf("decode %s: %w", rawURL, err)
	}
	return nil
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}
