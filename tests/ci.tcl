# ci.tcl --
#
# CI-focused test runner for Snack Tcl tests.
#
# Uses the same harness as all.tcl with defaults tuned for headless CI:
# - Skips tests that require live audio hardware or are currently unstable.
# - Allows overrides via environment variables.
#
# Environment overrides (space-separated glob patterns):
#   SNACK_TEST_INCLUDE_FILES  -> explicit file patterns to include
#   SNACK_TEST_SKIP_FILES     -> file patterns to skip
#   SNACK_TEST_SKIP_TESTS     -> test name patterns to skip
#

if {[lsearch [namespace children] ::tcltest] == -1} {
    package require tcltest
    namespace import ::tcltest::*
}

set ::tcltest::testSingleFile false
set ::tcltest::testsDirectory [file dirname [info script]]

set includeFilePatterns {}
set skipFilePatterns {audio.test mixer.test play.test record.test}
set ::tcltest::skip {fileio-1.4 formant-* pitch-1.3 power-1.1 sound-1.3}

if {[info exists ::env(SNACK_TEST_INCLUDE_FILES)]} {
    set includeFilePatterns [split $::env(SNACK_TEST_INCLUDE_FILES)]
}
if {[info exists ::env(SNACK_TEST_SKIP_FILES)]} {
    set skipFilePatterns [split $::env(SNACK_TEST_SKIP_FILES)]
}
if {[info exists ::env(SNACK_TEST_SKIP_TESTS)]} {
    set ::tcltest::skip [split $::env(SNACK_TEST_SKIP_TESTS)]
}

puts stdout "Tcl $tcl_patchLevel tests running in interp:  [info nameofexecutable]"
puts stdout "Tests running in working dir:  $::tcltest::testsDirectory"
if {[llength $::tcltest::skip] > 0} {
    puts stdout "Skipping tests that match:  $::tcltest::skip"
}
if {[llength $skipFilePatterns] > 0} {
    puts stdout "Skipping test files that match:  $skipFilePatterns"
}
if {[llength $includeFilePatterns] > 0} {
    puts stdout "Only sourcing test files that match:  $includeFilePatterns"
}

set timeCmd {clock format [clock seconds]}
puts stdout "Tests began at [eval $timeCmd]"

set selectedFiles {}
foreach file [lsort [::tcltest::getMatchingFiles]] {
    set tail [file tail $file]

    set include 1
    if {[llength $includeFilePatterns] > 0} {
        set include 0
        foreach pattern $includeFilePatterns {
            if {[string match $pattern $tail]} {
                set include 1
                break
            }
        }
    }
    if {!$include} {
        continue
    }

    set skipFile 0
    foreach pattern $skipFilePatterns {
        if {[string match $pattern $tail]} {
            set skipFile 1
            break
        }
    }
    if {$skipFile} {
        continue
    }

    lappend selectedFiles $file
}

foreach file $selectedFiles {
    set tail [file tail $file]
    puts stdout $tail
    if {[catch {source $file} msg]} {
        puts stdout $msg
    }
}

puts stdout "\nTests ended at [eval $timeCmd]"
::tcltest::cleanupTests 1
exit
