/*
* Copyright (c) 2012 Sprymix Inc.
* All rights reserved.
*
* See LICENSE for details.
**/


// %from metamagic.utils.lang.javascript import sx, class


$SXJSP = (function() {
    'use strict';

    var modules = {};

    var StdObject = {}.constructor,
        StdArray = [].constructor,
        hop = StdObject.prototype.hasOwnProperty,
        tos = StdObject.prototype.toString;

    var Array_some = StdArray.prototype.some;
    if (typeof Array_some == 'undefined') {
        Array_some = function(cb, scope) {
            var i = 0, len = this.length >>> 0;
            for (; i < len; i++) {
                if (cb.call(scope, this[i], i)) {
                    return true;
                }
            }
        }
    }
    var Array_slice = StdArray.prototype.slice;

    function Module(name, dct) {
        this.$name = name;
        this.$initialized = dct != null;

        for (var i in dct) {
            if (hop.call(dct, i) && i.length && i[0] != '$') {
                this[i] = dct[i];
            }
        }
    }

    function error(msg) {
        throw '$SXJSP: ' + msg;
    }

    function is(x, y) {
        return (x === y) ? (x !== 0 || 1 / x === 1 / y) : (x !== x && y !== y);
        //                             [1]                         [2]

        // [1]: 0 === -0, but they are not identical

        // [2]: NaN !== NaN, but they are identical.
        // NaNs are the only non-reflexive value, i.e., if x !== x,
        // then x is a NaN.
        // isNaN is broken: it converts its argument to number, so
        // isNaN("foo") => true
    }

    function EXPORTS(x) { return x; } // for static analysis

    return EXPORTS({
        /* private */

        _module: function(name, dct) {
            var parts = name.split('.'),
                i, len = parts.length,
                next = modules,
                next_sub,
                iter_name = [],
                part,
                mod,
                mod_name,
                mod_dct;

            if (!len) {
                error('invalid module name: "' +name + '"');
            }

            for (i = 0; i < len - 1; i++) {
                part = parts[i];
                iter_name.push(part);
                next_sub = next;
                if (next_sub.hasOwnProperty(part)) {
                    next = next_sub[part];
                } else {
                    next = next_sub[part] = new Module(iter_name.join('.'));
                }
            }

            mod_name = parts[len - 1];
            mod = next[mod_name];
            if (mod != null) {
                if (mod.$initialized) {
                    error('duplicate module? (' + name + ')');
                }
                for (i in dct) {
                    if (!mod.hasOwnProperty(i) && dct.hasOwnProperty(i)) {
                        mod[i] = dct[i];
                    }
                }
            } else {
                next[mod_name] = new Module(name, dct);
            }
        },

        _each: function(arg_cnt, it, cb, scope) {
            var t = tos.call(it);

            if (t == '[object Array]') {
                if (arg_cnt != 1) {
                    error('foreach supports only one iterator variable when iterating over arrays');
                }
                Array_some.call(it, cb, scope);
                return;
            }

            if (t == '[object Object]') {
                var k;
                if (arg_cnt == 2) {
                    for (k in it) {
                        if (hop.call(it, k)) {
                            if (cb.call(scope, k, it[k])) {
                                return;
                            }
                        }
                    }
                } else {
                    // arg_cnt == 1
                    for (k in it) {
                        if (hop.call(it, k)) {
                            if (cb.call(scope, [k, it[k]])) {
                                return;
                            }
                        }
                    }
                }
                return;
            }

            if (t == '[object String]' || t == '[object NodeList]') {
                if (arg_cnt != 1) {
                    error('foreach supports only one iterator variable when iterating over '
                          + 'strings or NodeList');
                }

                var len = it.length >>> 0, i = 0;

                for (; i < len; i++) {
                    if (cb.call(scope, it[i])) {
                        return;
                    }
                }
                return;
            }

            error('foreach: unsupported iterable: ' + it);
        },

        _validate_with: function(obj) {
            if (!obj.enter || tos.call(obj.enter) != '[object Function]'
                   || !obj.exit || tos.call(obj.exit) != '[object Function]') {
                error('with: context managers must have "enter" and "exit" methods');
            }
        },

        _slice1: function(obj, num) {
            return Array_slice.call(obj, num);
        },

        _is: is,
        _isnt: function(x, y) {
            return !is(x, y);
        },

        _newclass: sx.define.new_class,
        _super_method: sx.parent.find,
        _isinstance: sx.isinstance,

        /* public */

        isinstance: sx.isinstance,
        issubclass: sx.issubclass,
        BaseObject: sx.BaseObject,
        object: sx.object,
        type: sx.type,

        print: function() {
            if (typeof print != 'undefined') {
                return print.apply(this, arguments);
            }

            if (typeof console != 'undefined' && console.log) {
                return console.log.apply(console, arguments);
            }

            error('print function is unsupported');
        }
    });
})();