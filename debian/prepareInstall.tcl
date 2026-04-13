#!/usr/bin/tclsh

# find Tcl/Tk versions and Snack flavors in the args

set Package {}
set Versions {}
set Flavors {}
set Multiarch {}
set state none
foreach arg $argv {
    switch -- $arg {
        --package   { set state package }
        --versions  { set state versions }
        --flavors   { set state flavors }
        --multiarch { set state multiarch }
        default {
            switch -- $state {
                package   { set Package $arg }
                versions  { lappend Versions $arg }
                flavors   { lappend Flavors $arg }
                multiarch { set Multiarch $arg }
            }
        }
    }
}

# Packages:
#   tcl-snack
#   tcl-snack-dev
#   libsnack-oss
#   libsnack-alsa

proc LName {suffix version} {
    if {$version >= 9} {
        return ltcl9$suffix
    } else {
        return l$suffix
    }
}

proc LibName {suffix version} {
    if {$version >= 9} {
        return libtcl9$suffix.so
    } else {
        return lib$suffix.so
    }
}

proc SaveInstallData {InstallData FileName} {
    set fd [open $FileName w]
    puts $fd "#!/usr/bin/dh-exec"
    puts $fd [join $InstallData \n]
    close $fd
    file attribute $FileName -permissions rwxr-xr-x
}

set InstallDir /usr/lib/tcltk/$Multiarch/snack$Package

# libsnack-oss, libsnack-alsa
foreach flavor $Flavors {
    set InstallData {}
    foreach suffix {snack sound} {
        foreach version $Versions {
            lappend InstallData [list debian/$version/$flavor/lib$suffix.so => \
                                      $InstallDir/[LibName $suffix $version]]
        }
    }
    SaveInstallData $InstallData debian/libsnack-$flavor.install
}

# tcl-snack
set flavor [lindex $Flavors 0]
set InstallData [list [list pkgIndex.tcl $InstallDir/] \
                      [list unix/snack.tcl $InstallDir/]]
foreach version $Versions {
    foreach suffix {snackmpg snackogg} {
        lappend InstallData [list debian/$version/$flavor/lib$suffix.so => \
                                  $InstallDir/[LibName $suffix $version]]
    }
}
SaveInstallData $InstallData debian/tcl-snack.install

proc FixPkgIndex {versions flavor} {
    set fd [open pkgIndex.tcl w]
    foreach version [lsort -real -decreasing $versions] {
        puts $fd "if {\[package vsatisfies \[package provide Tcl\] $version\]} {"
        
        set ifd [open debian/$version/$flavor/pkgIndex.tcl]
        set indexdata [read $ifd]
        close $ifd

        if {$version >= 9} {
            set indexdata [string map {lib libtcl9} $indexdata]
        }

        puts $fd $indexdata
        puts $fd "}"
    }
    close $fd
}

FixPkgIndex $Versions $flavor

# tcl-snack-dev
set InstallData {{generic/jkAudIO.h /usr/include}
                 {generic/jkSound.h /usr/include}
                 {generic/snack.h /usr/include}
                 {generic/snackDecls.h /usr/include}}
set flavor [lindex $Flavors 0]
foreach version $Versions {
    lappend InstallData [list debian/$version/$flavor/libsnackstub$Package.a => \
                              $InstallDir/libsnackstub$version.a]
    set config debian/$version/$flavor/snackConfig.sh
    set fd [open $config]
    set cdata [read $fd]
    close $fd

    set cdata [regsub {(SNACK_INSTALL_PATH)='[^']*'} $cdata "\\1='$InstallDir'"]
    set cdata [regsub {(SNACK_LIB_SPEC)='[^']*'} $cdata "\\1='-L$InstallDir -[LName snack $version]'"]
    set cdata [regsub {(SNACK_STUB_LIB_FLAG)='[^']*'} $cdata "\\1='-L$InstallDir -lsnackstub$version'"]

    set fd [open $config w]
    puts -nonewline $fd $cdata
    close $fd

    lappend InstallData [list $config => $InstallDir/snackConfig$version.sh]
}
SaveInstallData $InstallData debian/tcl-snack-dev.install

set LinksData [list $InstallDir/snackConfig[lindex $Versions 0].sh $InstallDir/snackConfig.sh]
SaveInstallData $LinksData debian/tcl-snack-dev.links

