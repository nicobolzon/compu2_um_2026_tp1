import unittest

from src import procfs


class ProcfsParsingTests(unittest.TestCase):
    def test_parse_stat_supports_comm_with_spaces(self):
        fields = ["0"] * 50
        fields[0] = "S"  # field 3 state
        fields[1] = "42"  # field 4 ppid
        fields[2] = "7"  # field 5 pgid
        fields[3] = "8"  # field 6 sid
        fields[7] = "11"  # field 10 minflt
        fields[10] = "2"  # field 13 cmajflt
        fields[11] = "100"  # field 14 utime
        fields[12] = "50"  # field 15 stime
        fields[15] = "20"  # field 18 priority
        fields[16] = "5"  # field 19 nice
        fields[17] = "3"  # field 20 num_threads
        fields[37] = "0"  # field 40 rt_priority
        fields[38] = "0"  # field 41 policy
        parsed = procfs.parse_stat_content("123 (python worker) " + " ".join(fields))

        self.assertEqual(parsed["pid"], 123)
        self.assertEqual(parsed["comm"], "python worker")
        self.assertEqual(parsed["state"], "S")
        self.assertEqual(parsed["ppid"], 42)
        self.assertEqual(parsed["utime"], 100)
        self.assertEqual(parsed["stime"], 50)
        self.assertEqual(parsed["num_threads"], 3)

    def test_parse_status_content(self):
        status = procfs.parse_status_content(
            "Name:\tpython\n"
            "Uid:\t1000\t1000\t1000\t1000\n"
            "VmRSS:\t  2048 kB\n"
        )

        self.assertEqual(status["Name"], "python")
        self.assertEqual(procfs.parse_kb(status["VmRSS"]), 2048)
        uid, gid, user, group = procfs.uid_gid_from_status({**status, "Gid": "1000 1000 1000 1000"})
        self.assertEqual(uid, 1000)
        self.assertEqual(gid, 1000)
        self.assertTrue(user)
        self.assertTrue(group)

    def test_signal_mask_decoding(self):
        self.assertIn("SIGINT", procfs.signal_names_from_mask("0000000000000002"))
        self.assertEqual(procfs.signal_names_from_mask("0000000000000000"), [])

    def test_cpu_percent_uses_jiffy_deltas(self):
        cpu = procfs.calc_cpu_percent(100, 125, 1000, 1100, cpu_count=4)
        self.assertEqual(cpu, 100.0)

    def test_meminfo_parser(self):
        parsed = procfs.parse_meminfo_content("MemTotal:       1000 kB\nCached:          250 kB\n")
        self.assertEqual(parsed["MemTotal"], 1000)
        self.assertEqual(parsed["Cached"], 250)


if __name__ == "__main__":
    unittest.main()
