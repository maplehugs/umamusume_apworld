// umapd_archipelago: a Hachimi Edge plugin that keeps the running game in sync
// with the UmamusumeX server, without a restart or a trip to the title screen.
//
// The server touches two files in the game's hachimi folder:
// - umapd_master.version after every change it commits to master.mdb (custom
//   banners, Legend races, event dates, the Archipelago Legend ladder): the
//   plugin calls the game's own Gallop.MasterDataManager.UnloadDatabases(), so
//   every master table drops its cached rows and the next lookup reads the new
//   ones.
// - umapd_account.version when the account changes behind the client's back
//   (Archipelago seed switch, items from the multiworld, a restored save): the
//   plugin waits until the player is on the home screen (no dialog, no screen
//   change running) and runs the game's own day-change re-login
//   (Gallop.DateChange.OnClickDateChange -> DayChangeHub view ->
//   MainGameInitializer.InitializeMainGame), which logs in again, applies a
//   fresh load/index and returns to the home screen.
// Both are checked once a second from Gallop.GameSystem.FixedUpdate (main
// thread; Hachimi itself hooks GameSystem.Update/LateUpdate, and MinHook allows
// one hook per function).
// See RE_NOTES.md. Build/install: README.md.

#include <windows.h>

typedef void *(*get_api_fn)(const char *name);
typedef void *(*hachimi_instance_fn)(void);
typedef void *(*get_interceptor_fn)(void *hachimi);
typedef void *(*interceptor_hook_fn)(void *interceptor, void *orig, void *hook);
typedef void *(*get_image_fn)(const char *assembly);
typedef void *(*get_class_fn)(void *image, const char *ns, const char *name);
typedef void *(*get_method_addr_fn)(void *klass, const char *name, int args);
typedef void (*log_fn)(int level, const char *target, const char *message);
typedef void *(*ptr_fn)(void *p);
typedef const char *(*name_fn)(void *p);
typedef void *(*class_method_fn)(void *klass, const char *name, int args);
typedef void *(*class_field_fn)(void *klass, const char *name);
typedef void (*field_static_get_fn)(void *field, void *out);
typedef int (*field_flags_fn)(void *field);
typedef unsigned (*method_flags_fn)(void *method, unsigned *iflags);
typedef void *(*runtime_invoke_fn)(void *method, void *obj, void **params, void **exc);

enum { LOG_ERROR = 1, LOG_WARN = 2, LOG_INFO = 3 };
#define TAG "umapd_archipelago"
#define STATIC 0x10  // FIELD_ATTRIBUTE_STATIC == METHOD_ATTRIBUTE_STATIC
#define SETTLE_MS 3000  // items often arrive in bursts: wait for the last one

static log_fn LOG;
static char MASTER_PATH[MAX_PATH], ACCOUNT_PATH[MAX_PATH];
static void *IMAGE;
static get_class_fn get_class;
static ptr_fn class_parent, object_class, unbox;
static name_fn class_name;
static class_method_fn class_method;
static class_field_fn class_field;
static field_static_get_fn field_static_get;
static field_flags_fn field_flags;
static method_flags_fn method_flags;
static runtime_invoke_fn runtime_invoke;

typedef void (*update_fn)(void *self, void *method);
static update_fn UPDATE_ORIG;

static void *klass(const char *name) { return get_class(IMAGE, "Gallop", name); }

// A manager singleton: the instance on the class or its parents (Singleton<T>),
// as a static field or a get_Instance getter.
static void *instance(void *k) {
    static const char *fields[] = {"_instance", "instance", "s_instance", 0};
    for (; k; k = class_parent(k)) {
        for (int i = 0; fields[i]; i++) {
            void *f = class_field(k, fields[i]), *v = NULL;
            if (f && (field_flags(f) & STATIC)) field_static_get(f, &v);
            if (v) return v;
        }
        void *m = class_method(k, "get_Instance", 0), *v = NULL, *exc = NULL;
        if (m && (v = runtime_invoke(m, NULL, NULL, &exc)) && !exc) return v;
    }
    return NULL;
}

// Call Gallop.<cls>.<name> (static, or on the class's singleton). Returns 0 when
// the method or instance is missing or it threw; *out gets the (boxed) result.
static int call(const char *cls, const char *name, int argc, void **args, void **out) {
    void *k = klass(cls), *m = k ? class_method(k, name, argc) : NULL;
    if (!m) return 0;
    unsigned iflags;
    void *obj = (method_flags(m, &iflags) & STATIC) ? NULL : instance(k), *exc = NULL;
    if (!obj && !(method_flags(m, &iflags) & STATIC)) return 0;
    void *r = runtime_invoke(m, obj, args, &exc);
    if (out) *out = r;
    return exc == NULL;
}

static int call_bool(const char *cls, const char *name, int fallback) {
    void *r = NULL;
    return call(cls, name, 0, NULL, &r) && r ? *(unsigned char *)unbox(r) : fallback;
}

static void reload_master(void) {
    LOG(LOG_INFO, TAG, call("MasterDataManager", "UnloadDatabases", 0, NULL, NULL)
                           ? "master.mdb changed: master data reloaded"
                           : "master.mdb changed: UnloadDatabases failed (not found, or threw)");
}

// 1 when the player is on the home screen with nothing else going on.
static int at_home(void) {
    static char last[96];
    void *view = NULL;
    if (call_bool("SceneManager", "get_IsRunChangeView", 1) || call_bool("SceneManager", "get_IsRunChangeScene", 1) ||
        call_bool("DialogManager", "get_IsExistDialog", 1))
        return 0;
    const char *name = call("SceneManager", "GetCurrentViewBase", 0, NULL, &view) && view
                           ? class_name(object_class(view)) : "(current screen unreadable)";
    if (name[0] == 'H' && name[1] == 'o' && name[2] == 'm' && name[3] == 'e') return 1;
    if (lstrcmpA(last, name)) {  // once per screen
        lstrcpynA(last, name, sizeof last);
        char line[160];
        wsprintfA(line, "account changed: waiting for the home screen (now on %s)", name);
        LOG(LOG_INFO, TAG, line);
    }
    return 0;
}

static void relogin(void) {
    void *args[1] = {NULL};  // the dialog: unused
    LOG(LOG_INFO, TAG, call("DateChange", "OnClickDateChange", 1, args, NULL)
                           ? "account changed: logging in again (day-change reload)"
                           : "account changed: OnClickDateChange failed (not found, or threw)");
}

// 1 when the file's write time changed since the last call (a file missing at
// the first call counts as "never written", so its creation is a change).
static int changed(const char *path, FILETIME *seen) {
    WIN32_FILE_ATTRIBUTE_DATA a;
    FILETIME now = {0, 0};
    if (GetFileAttributesExA(path, GetFileExInfoStandard, &a)) now = a.ftLastWriteTime;
    if (seen->dwHighDateTime == 0xFFFFFFFF) {  // first call: just record
        *seen = now;
        return 0;
    }
    int c = CompareFileTime(&now, seen) != 0;
    *seen = now;
    return c;
}

static void update_hook(void *self, void *method) {
    static ULONGLONG next, account_at;
    static FILETIME master_seen = {0, 0xFFFFFFFF}, account_seen = {0, 0xFFFFFFFF};
    ULONGLONG now = GetTickCount64();
    if (now >= next) {
        next = now + 1000;
        if (changed(MASTER_PATH, &master_seen)) reload_master();
        if (changed(ACCOUNT_PATH, &account_seen)) account_at = now;
        if (account_at && now - account_at >= SETTLE_MS && at_home()) {
            account_at = 0;
            relogin();
        }
    }
    UPDATE_ORIG(self, method);
}

static void sibling(char *out, const char *name) {
    HMODULE self = NULL;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCSTR)&sibling, &self);
    DWORD n = GetModuleFileNameA(self, out, MAX_PATH);
    while (n > 0 && out[n - 1] != '\\' && out[n - 1] != '/') n--;
    lstrcpynA(out + n, name, MAX_PATH - (int)n);
}

__declspec(dllexport) int hachimi_init_v3(get_api_fn api, int version) {
    if (version < 3) return 0;
    LOG = (log_fn)api("log");
    get_api_fn sym = (get_api_fn)api("il2cpp_resolve_symbol");
    if (!LOG || !sym || !api("interceptor_hook")) return 0;
    class_parent = (ptr_fn)sym("il2cpp_class_get_parent");
    object_class = (ptr_fn)sym("il2cpp_object_get_class");
    unbox = (ptr_fn)sym("il2cpp_object_unbox");
    class_name = (name_fn)sym("il2cpp_class_get_name");
    class_method = (class_method_fn)sym("il2cpp_class_get_method_from_name");
    class_field = (class_field_fn)sym("il2cpp_class_get_field_from_name");
    field_static_get = (field_static_get_fn)sym("il2cpp_field_static_get_value");
    field_flags = (field_flags_fn)sym("il2cpp_field_get_flags");
    method_flags = (method_flags_fn)sym("il2cpp_method_get_flags");
    runtime_invoke = (runtime_invoke_fn)sym("il2cpp_runtime_invoke");
    if (!class_parent || !object_class || !unbox || !class_name || !class_method || !class_field ||
        !field_static_get || !field_flags || !method_flags || !runtime_invoke) {
        LOG(LOG_ERROR, TAG, "il2cpp exports missing");
        return 0;
    }
    sibling(MASTER_PATH, "umapd_master.version");
    sibling(ACCOUNT_PATH, "umapd_account.version");

    IMAGE = ((get_image_fn)api("il2cpp_get_assembly_image"))("umamusume.dll");
    get_class = (get_class_fn)api("il2cpp_get_class");
    void *game_system = IMAGE ? klass("GameSystem") : NULL;
    void *update = game_system ? ((get_method_addr_fn)api("il2cpp_get_method_addr"))(game_system, "FixedUpdate", 0) : NULL;
    if (!update || !klass("MasterDataManager") || !klass("DateChange") || !klass("SceneManager")) {
        LOG(LOG_ERROR, TAG, "game classes not found; the game may have changed");
        return 0;
    }
    void *interceptor = ((get_interceptor_fn)api("hachimi_get_interceptor"))(((hachimi_instance_fn)api("hachimi_instance"))());
    UPDATE_ORIG = (update_fn)((interceptor_hook_fn)api("interceptor_hook"))(interceptor, update, (void *)update_hook);
    LOG(LOG_INFO, TAG, UPDATE_ORIG ? "GameSystem.FixedUpdate hooked: watching" : "hook failed (GameSystem.FixedUpdate)");
    LOG(LOG_INFO, TAG, MASTER_PATH);
    return UPDATE_ORIG != NULL;
}
